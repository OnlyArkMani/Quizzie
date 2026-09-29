"""
Attempt integrity: durable auto-save, resume, server-side deadline,
idempotent submit, answer-key hiding.

Time is controlled by moving the attempt's started_at/deadline into the past
(the server only trusts its own clock, so that's the honest way to simulate
"the exam ran out").
"""
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from app.models.attempt import AttemptStatus, ExamAttempt, Response
from app.models.exam import Exam, ExamStatus
from app.models.question import Option, Question, QuestionType

_PATCH_TARGET = "app.api.v1.attempts.evaluate_attempt_task"


def _no_celery():
    m = MagicMock()
    m.apply_async.side_effect = Exception("no broker in tests")
    return patch(_PATCH_TARGET, m)


def _start(client, headers, exam_id):
    r = client.post("/api/v1/attempts/start", json={"exam_id": str(exam_id)}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _save(client, headers, attempt_id, question_id, option_ids, seq, text=None):
    return client.post(
        f"/api/v1/attempts/{attempt_id}/auto-save",
        json={"responses": [{
            "question_id": str(question_id),
            "selected_option_ids": [str(o) for o in option_ids],
            "answer_text": text,
            "client_seq": seq,
        }]},
        headers=headers,
    )


def _submit(client, headers, attempt_id, responses=None, key=None):
    h = dict(headers)
    if key:
        h["Idempotency-Key"] = key
    with _no_celery():
        return client.post(
            f"/api/v1/attempts/{attempt_id}/submit",
            json={"responses": responses or []},
            headers=h,
        )


def _expire(db, attempt_id, seconds_past_deadline):
    """Rewind the attempt so its deadline was `seconds_past_deadline` ago."""
    a = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    a.deadline = datetime.utcnow() - timedelta(seconds=seconds_past_deadline)
    a.started_at = a.deadline - timedelta(minutes=60)
    db.commit()


# ── Start / deadline ─────────────────────────────────────────────────────────

class TestStartSetsDeadline:
    def test_deadline_is_start_plus_duration(self, client, student_headers, live_exam, db):
        exam, *_ = live_exam
        data = _start(client, student_headers, exam.id)
        a = db.query(ExamAttempt).filter(ExamAttempt.id == data["id"]).first()
        assert a.deadline is not None
        assert a.deadline - a.started_at == timedelta(minutes=exam.duration_minutes)
        assert data["deadline"] is not None

    def test_expired_attempt_is_not_resumed(self, client, student_headers, live_exam, db):
        exam, *_ = live_exam
        first = _start(client, student_headers, exam.id)
        _expire(db, first["id"], seconds_past_deadline=120)
        second = _start(client, student_headers, exam.id)
        assert second["id"] != first["id"]
        old = db.query(ExamAttempt).filter(ExamAttempt.id == first["id"]).first()
        db.refresh(old)
        assert old.status == AttemptStatus.SUBMITTED
        assert old.submitted_at == old.deadline          # closed AT the deadline


# ── Durable auto-save ────────────────────────────────────────────────────────

class TestAutoSave:
    def test_autosave_persists_and_state_returns_it(self, client, student_headers, live_exam):
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        r = _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=1)
        assert r.status_code == 200 and r.json()["saved"] == 1

        # Simulate a browser crash + reload: the page rebuilds from /state.
        st = client.get(f"/api/v1/attempts/{attempt['id']}/state", headers=student_headers).json()
        assert st["status"] == "in_progress"
        assert st["remaining_seconds"] > 0
        assert st["responses"] == [{
            "question_id": str(q.id),
            "selected_option_ids": [str(correct.id)],
            "answer_text": None,
            "marked_for_review": False,
            "client_seq": 1,
        }]

    def test_replaying_same_save_is_idempotent(self, client, student_headers, live_exam, db):
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        for _ in range(3):
            assert _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=5).status_code == 200
        rows = db.query(Response).filter(Response.attempt_id == attempt["id"]).all()
        assert len(rows) == 1

    def test_out_of_order_save_cannot_overwrite_newer_answer(self, client, student_headers, live_exam, db):
        exam, q, correct, wrong = live_exam
        attempt = _start(client, student_headers, exam.id)
        # The newer edit (seq 10) arrives first; a delayed retry of an older
        # edit (seq 3) arrives after it. Arrival order must not matter.
        _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=10)
        _save(client, student_headers, attempt["id"], q.id, [wrong.id], seq=3)
        row = db.query(Response).filter(Response.attempt_id == attempt["id"]).one()
        db.refresh(row)
        assert row.selected_option_ids == [correct.id]
        assert row.client_seq == 10

    def test_cannot_answer_question_from_another_exam(self, client, student_headers, live_exam, db, examiner_user):
        exam, *_ = live_exam
        other = Exam(title="O", description="", duration_minutes=10, total_marks=1,
                     pass_percentage=40, status=ExamStatus.LIVE, created_by=examiner_user.id)
        db.add(other)
        db.commit()
        foreign_q = Question(exam_id=other.id, question_text="x", question_type=QuestionType.SINGLE,
                             marks=1, display_order=1)
        db.add(foreign_q)
        db.commit()
        attempt = _start(client, student_headers, exam.id)
        r = _save(client, student_headers, attempt["id"], foreign_q.id, [], seq=1)
        assert r.status_code == 422

    def test_crash_before_submit_keeps_answers(self, client, student_headers, live_exam):
        """The student's tab dies; they come back and submit an empty payload."""
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=1)
        r = _submit(client, student_headers, attempt["id"], responses=[])
        assert r.status_code == 200, r.text
        assert r.json()["score"] == 100.0

    def test_save_after_submit_is_rejected(self, client, student_headers, live_exam):
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        _submit(client, student_headers, attempt["id"])
        r = _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=2)
        assert r.status_code == 409


# ── Server-authoritative deadline ────────────────────────────────────────────

class TestDeadline:
    def test_save_after_deadline_plus_grace_is_rejected(self, client, student_headers, live_exam, db):
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        _expire(db, attempt["id"], seconds_past_deadline=120)   # grace is 30 s
        r = _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=1)
        assert r.status_code == 409
        a = db.query(ExamAttempt).filter(ExamAttempt.id == attempt["id"]).first()
        db.refresh(a)
        assert a.status == AttemptStatus.SUBMITTED

    def test_save_within_grace_is_accepted(self, client, student_headers, live_exam, db):
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        _expire(db, attempt["id"], seconds_past_deadline=5)     # inside 30 s grace
        r = _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=1)
        assert r.status_code == 200

    def test_late_submit_payload_is_ignored(self, client, student_headers, live_exam, db):
        """
        A tampered client keeps answering after time's up and submits late.
        Only what was durably saved before the deadline counts.
        """
        exam, q, correct, wrong = live_exam
        attempt = _start(client, student_headers, exam.id)
        _save(client, student_headers, attempt["id"], q.id, [wrong.id], seq=1)   # in time
        _expire(db, attempt["id"], seconds_past_deadline=600)
        r = _submit(client, student_headers, attempt["id"], responses=[{
            "question_id": str(q.id), "selected_option_ids": [str(correct.id)], "client_seq": 99,
        }])
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["late"] is True
        assert body["score"] == 0.0                              # the late "fix" was dropped
        a = db.query(ExamAttempt).filter(ExamAttempt.id == attempt["id"]).first()
        db.refresh(a)
        assert a.time_taken_seconds == exam.duration_minutes * 60

    def test_results_finalize_an_abandoned_attempt(self, client, student_headers, live_exam, db):
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        _save(client, student_headers, attempt["id"], q.id, [correct.id], seq=1)
        _expire(db, attempt["id"], seconds_past_deadline=3600)
        r = client.get(f"/api/v1/attempts/{attempt['id']}/results", headers=student_headers)
        assert r.status_code == 200, r.text
        assert r.json()["score"] == 100.0


# ── Idempotent submit ─────────────────────────────────────────────────────────

class TestIdempotentSubmit:
    def test_retry_with_same_key_is_a_replay(self, client, student_headers, live_exam):
        exam, q, correct, _ = live_exam
        attempt = _start(client, student_headers, exam.id)
        payload = [{"question_id": str(q.id), "selected_option_ids": [str(correct.id)], "client_seq": 1}]
        r1 = _submit(client, student_headers, attempt["id"], payload, key="k-123")
        r2 = _submit(client, student_headers, attempt["id"], payload, key="k-123")
        assert r1.status_code == 200 and r1.json()["idempotent_replay"] is False
        assert r2.status_code == 200 and r2.json()["idempotent_replay"] is True

    def test_different_key_is_rejected(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        attempt = _start(client, student_headers, exam.id)
        assert _submit(client, student_headers, attempt["id"], key="a").status_code == 200
        r = _submit(client, student_headers, attempt["id"], key="b")
        assert r.status_code == 400
        assert r.json()["detail"] == "Attempt already submitted"


# ── Answer key never reaches students ────────────────────────────────────────

class TestQuestionPayload:
    def test_student_does_not_receive_answer_key(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        qs = client.get(f"/api/v1/exams/{exam.id}/questions", headers=student_headers).json()
        assert qs[0]["question_type"] == "single"
        assert "reference_answer" not in qs[0]
        for opt in qs[0]["options"]:
            assert "is_correct" not in opt

    def test_owner_examiner_receives_answer_key(self, client, examiner_headers, live_exam):
        exam, *_ = live_exam
        qs = client.get(f"/api/v1/exams/{exam.id}/questions", headers=examiner_headers).json()
        assert any(o["is_correct"] for o in qs[0]["options"])

    def test_student_view_after_examiner_warmed_cache(self, client, student_headers, examiner_headers, live_exam):
        """The cache stores the full payload; stripping happens per request."""
        exam, *_ = live_exam
        client.get(f"/api/v1/exams/{exam.id}/questions", headers=examiner_headers)
        qs = client.get(f"/api/v1/exams/{exam.id}/questions", headers=student_headers).json()
        assert all("is_correct" not in o for o in qs[0]["options"])

    def test_other_examiner_forbidden(self, client, live_exam, db):
        from app.core.security import get_password_hash
        from app.models.user import User, UserRole
        from tests.conftest import make_token

        exam, *_ = live_exam
        other = User(email="other-ex@test.com", password_hash=get_password_hash("pw"),
                     full_name="Other", role=UserRole.EXAMINER, is_verified=True)
        db.add(other)
        db.commit()
        r = client.get(f"/api/v1/exams/{exam.id}/questions",
                       headers={"Authorization": f"Bearer {make_token(other)}"})
        assert r.status_code == 403


# ── Health recovery is server-policed ────────────────────────────────────────

class TestRecoveryPolicy:
    def test_no_recovery_right_after_violation(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        attempt = _start(client, student_headers, exam.id)
        client.post("/api/v1/monitor/enhanced/violation", json={
            "attempt_id": attempt["id"], "event_type": "tab_switch",
            "flags": [{"type": "tab_switch", "severity": "high", "message": "x"}],
        }, headers=student_headers)
        r = client.post("/api/v1/monitor/enhanced/recover",
                        json={"attempt_id": attempt["id"], "amount": 20}, headers=student_headers)
        assert r.status_code == 200
        assert r.json()["eligible"] is False and r.json()["recovered"] == 0

    def test_recovery_spam_is_capped(self, client, student_headers, live_exam, db):
        exam, *_ = live_exam
        attempt = _start(client, student_headers, exam.id)
        a = db.query(ExamAttempt).filter(ExamAttempt.id == attempt["id"]).first()
        a.current_health = 50
        db.commit()
        gained = 0
        for _ in range(10):
            r = client.post("/api/v1/monitor/enhanced/recover",
                            json={"attempt_id": attempt["id"], "amount": 20}, headers=student_headers)
            gained += r.json()["recovered"]
        assert gained == 3        # one grant per minute, server-chosen amount
