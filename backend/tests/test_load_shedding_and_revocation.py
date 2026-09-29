"""
Second round: results-polling, health read model, frame mailbox (load
shedding), violation counter, token revocation.
"""
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event

from app.core import frame_mailbox, redis_client
from app.core.config import settings
from app.models.attempt import AttemptStatus, ExamAttempt
from app.services import evaluation_dispatch

needs_redis = pytest.mark.skipif(redis_client.get_sync_redis() is None, reason="needs Redis")


def _start(client, headers, exam_id):
    r = client.post("/api/v1/attempts/start", json={"exam_id": str(exam_id)}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


class _SQL:
    """Collect SQL statements executed on the test connection."""

    def __init__(self, db):
        self.bind = db.get_bind()
        self.statements = []

    def __enter__(self):
        event.listen(self.bind, "before_cursor_execute", self._on)
        return self

    def __exit__(self, *exc):
        event.remove(self.bind, "before_cursor_execute", self._on)

    def _on(self, conn, cursor, statement, params, context, executemany):
        self.statements.append(statement)

    def matching(self, *needles):
        return [s for s in self.statements if all(n in s for n in needles)]


# ── Results polling no longer re-evaluates ──────────────────────────────────

@needs_redis
class TestResultsPolling:
    def _submit_queued(self, client, headers, attempt_id, monkeypatch):
        monkeypatch.setattr(settings, "EVALUATION_MODE", "auto")
        task = MagicMock()
        task.apply_async.return_value = MagicMock(id="task-1")
        with patch("app.api.v1.attempts.evaluate_attempt_task", task):
            r = client.post(f"/api/v1/attempts/{attempt_id}/submit",
                            json={"responses": []}, headers=headers)
        assert r.status_code == 200 and r.json()["status"] == "evaluating"
        return task

    def test_pending_evaluation_returns_202_without_evaluating(
        self, client, student_headers, live_exam, monkeypatch
    ):
        exam, *_ = live_exam
        aid = _start(client, student_headers, exam.id)
        self._submit_queued(client, student_headers, aid, monkeypatch)

        with patch("app.api.v1.attempts.EvaluationService") as svc:
            for _ in range(5):                       # a student hammering refresh
                r = client.get(f"/api/v1/attempts/{aid}/results", headers=student_headers)
                assert r.status_code == 202
                assert r.json()["status"] == "evaluating"
            svc.assert_not_called()

    def test_stuck_task_falls_back_to_one_inline_evaluation(
        self, client, student_headers, live_exam, monkeypatch
    ):
        exam, *_ = live_exam
        aid = _start(client, student_headers, exam.id)
        self._submit_queued(client, student_headers, aid, monkeypatch)
        evaluation_dispatch.clear_pending(aid)        # the worker died; marker expired

        r = client.get(f"/api/v1/attempts/{aid}/results", headers=student_headers)
        assert r.status_code == 200 and r.json()["status"] == "evaluated"

    def test_concurrent_poller_waits_for_the_inline_evaluator(
        self, client, student_headers, live_exam, monkeypatch
    ):
        exam, *_ = live_exam
        aid = _start(client, student_headers, exam.id)
        self._submit_queued(client, student_headers, aid, monkeypatch)
        evaluation_dispatch.clear_pending(aid)
        assert evaluation_dispatch.acquire_inline_lock(aid)   # another poller is evaluating

        r = client.get(f"/api/v1/attempts/{aid}/results", headers=student_headers)
        assert r.status_code == 202
        evaluation_dispatch.release_inline_lock(aid)


# ── Violation counter instead of COUNT(*) ───────────────────────────────────

class TestViolationCounter:
    def test_violation_path_runs_no_count_query(self, client, student_headers, live_exam, db):
        exam, *_ = live_exam
        aid = _start(client, student_headers, exam.id)
        body = {"attempt_id": aid, "event_type": "tab_switch",
                "flags": [{"type": "tab_switch", "severity": "high", "message": "x"}]}
        client.post("/api/v1/monitor/enhanced/violation", json=body, headers=student_headers)
        with _SQL(db) as sql:
            r = client.post("/api/v1/monitor/enhanced/violation", json=body, headers=student_headers)
        assert r.status_code == 200
        assert r.json()["health"]["violations_count"] == 2
        assert sql.matching("count(", "cheat_logs") == []


# ── Health read model ────────────────────────────────────────────────────────

@needs_redis
class TestHealthSnapshot:
    def test_student_health_poll_is_served_from_redis(self, client, student_headers, live_exam, db):
        exam, *_ = live_exam
        aid = _start(client, student_headers, exam.id)
        client.post("/api/v1/monitor/enhanced/violation", json={
            "attempt_id": aid, "event_type": "tab_switch",
            "flags": [{"type": "tab_switch", "severity": "high", "message": "x"}]},
            headers=student_headers)                    # publishes a snapshot
        with _SQL(db) as sql:
            r = client.get(f"/api/v1/monitor/enhanced/attempt/{aid}/health", headers=student_headers)
        assert r.status_code == 200
        assert r.json()["violations_count"] == 1
        assert sql.statements == []                     # zero DB work

    def test_other_student_cannot_read_snapshot(self, client, student_headers, live_exam, db):
        from app.core.security import get_password_hash
        from app.models.user import User, UserRole
        from tests.conftest import make_token

        exam, *_ = live_exam
        aid = _start(client, student_headers, exam.id)
        client.post("/api/v1/monitor/enhanced/violation", json={
            "attempt_id": aid, "event_type": "tab_switch",
            "flags": [{"type": "tab_switch", "severity": "high", "message": "x"}]},
            headers=student_headers)
        other = User(email="snoop@test.com", password_hash=get_password_hash("pw"),
                     full_name="S", role=UserRole.STUDENT, is_verified=True)
        db.add(other)
        db.commit()
        r = client.get(f"/api/v1/monitor/enhanced/attempt/{aid}/health",
                       headers={"Authorization": f"Bearer {make_token(other)}"})
        assert r.status_code == 403                     # owner check before the cache


# ── Frame mailbox: coalescing / load shedding ────────────────────────────────

@needs_redis
class TestFrameMailbox:
    def test_only_first_upload_enqueues_and_worker_gets_latest(self):
        outcomes = [frame_mailbox.post("frame", "att-m", f"img{i}".encode()) for i in range(10)]
        assert outcomes[0] == frame_mailbox.ENQUEUE
        assert outcomes[1:] == [frame_mailbox.COALESCED] * 9
        assert frame_mailbox.take("frame", "att-m") == b"img9"      # newest, not oldest
        assert frame_mailbox.take("frame", "att-m") is None         # claimed once
        assert frame_mailbox.post("frame", "att-m", b"next") == frame_mailbox.ENQUEUE

    def test_attempts_are_independent(self):
        assert frame_mailbox.post("frame", "a1", b"x") == frame_mailbox.ENQUEUE
        assert frame_mailbox.post("frame", "a2", b"y") == frame_mailbox.ENQUEUE
        assert frame_mailbox.post("audio", "a1", b"z") == frame_mailbox.ENQUEUE

    def test_upload_burst_enqueues_one_task(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        aid = _start(client, student_headers, exam.id)
        task = MagicMock()
        task.apply_async.return_value = MagicMock(id="t")
        with patch("app.worker.tasks.proctoring_tasks.analyze_latest_task", task):
            codes = []
            for i in range(8):                               # within the 8/5 s rate limit
                r = client.post("/api/v1/monitor/frame", data={"attempt_id": aid},
                                files={"file": ("f.jpg", f"jpeg-{i}".encode(), "image/jpeg")},
                                headers=student_headers)
                codes.append(r.json())
        assert task.apply_async.call_count == 1
        assert sum(1 for c in codes if c.get("coalesced")) == 7
        assert frame_mailbox.take("frame", aid) == b"jpeg-7"

    def test_failed_enqueue_releases_the_slot(self):
        assert frame_mailbox.post("frame", "att-f", b"1") == frame_mailbox.ENQUEUE
        frame_mailbox.cancel_pending("frame", "att-f")        # broker refused the task
        assert frame_mailbox.post("frame", "att-f", b"2") == frame_mailbox.ENQUEUE


# ── Token revocation ─────────────────────────────────────────────────────────

class TestTokenRevocation:
    def _login(self, client):
        r = client.post("/api/v1/auth/login",
                        json={"email": "student@test.com", "password": "password123"})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def test_logout_revokes_the_token(self, client, student_user):
        h = self._login(client)
        assert client.get("/api/v1/auth/me", headers=h).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=h).status_code == 200
        r = client.get("/api/v1/auth/me", headers=h)
        assert r.status_code == 401
        assert r.json()["detail"] == "Session has been revoked"

    def test_logout_revokes_every_session(self, client, student_user):
        laptop, phone = self._login(client), self._login(client)
        client.post("/api/v1/auth/logout", headers=laptop)
        assert client.get("/api/v1/auth/me", headers=phone).status_code == 401
        fresh = self._login(client)                       # logging in again works
        assert client.get("/api/v1/auth/me", headers=fresh).status_code == 200

    def test_pre_upgrade_tokens_still_work(self, client, student_headers):
        # conftest mints tokens without a "tv" claim, like tokens issued before
        # this deploy: they must keep working while token_version is 0.
        assert client.get("/api/v1/auth/me", headers=student_headers).status_code == 200

    def test_revocation_beats_the_user_cache(self, client, student_user):
        h = self._login(client)
        client.get("/api/v1/auth/me", headers=h)            # user now cached in Redis
        client.post("/api/v1/auth/logout", headers=h)       # must invalidate it
        assert client.get("/api/v1/auth/me", headers=h).status_code == 401


# ── Login throttling: per account, not per (proxy) IP ────────────────────────

class TestLoginThrottle:
    def test_account_is_throttled_after_ten_attempts(self, client, student_user):
        codes = [client.post("/api/v1/auth/login",
                             json={"email": "student@test.com", "password": "wrong"}).status_code
                 for _ in range(11)]
        assert codes[:10] == [401] * 10
        assert codes[10] == 429

    def test_other_accounts_behind_the_same_ip_are_not_blocked(self, client, student_user, examiner_user):
        for _ in range(11):
            client.post("/api/v1/auth/login", json={"email": "student@test.com", "password": "wrong"})
        r = client.post("/api/v1/auth/login", json={"email": "examiner@test.com", "password": "password123"})
        assert r.status_code == 200      # a classmate on the same NAT still gets in
