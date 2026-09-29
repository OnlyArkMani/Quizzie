"""
Redis-backed shared state: rate limiting, flag smoothing, cache stampede
protection, auth user cache, and pub/sub fan-out to WebSockets.

"Two replicas" are simulated honestly: the Redis-backed code keeps no state in
the process, so two independent clients/processes see the same counters. The
in-process fallback is exercised as the contrast (it is per-process by design).
"""
import asyncio
import threading
import time

import pytest
from sqlalchemy import event

from app.core import events, rate_limit, redis_client
from app.core.cache import RedisCache

pytestmark = pytest.mark.skipif(
    redis_client.get_sync_redis() is None, reason="needs a Redis server"
)


# ── Rate limiting ────────────────────────────────────────────────────────────

class TestRateLimit:
    def test_sliding_window_admits_exactly_the_limit(self):
        results = [rate_limit.allow_sync("t:a1", 8, 5.0) for _ in range(12)]
        assert results.count(True) == 8

    def test_limit_is_shared_across_replicas(self):
        """
        Two 'replicas' hitting the same key concurrently: together they get the
        limit once, not once each. (The old per-process dict gave each replica
        its own budget.)
        """
        admitted = []
        lock = threading.Lock()

        def replica():
            for _ in range(10):
                ok = rate_limit.allow_sync("t:shared", 8, 5.0)
                with lock:
                    admitted.append(ok)

        ts = [threading.Thread(target=replica) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert admitted.count(True) == 8

    def test_in_process_fallback_is_per_process(self):
        a, b = rate_limit._LocalWindows(), rate_limit._LocalWindows()
        total = sum(a.allow("k", 8, 5.0) for _ in range(10)) + sum(b.allow("k", 8, 5.0) for _ in range(10))
        assert total == 16      # exactly the bug the Redis version fixes

    def test_window_slides(self):
        for _ in range(2):
            assert rate_limit.allow_sync("t:slide", 2, 0.3)
        assert not rate_limit.allow_sync("t:slide", 2, 0.3)
        time.sleep(0.35)
        assert rate_limit.allow_sync("t:slide", 2, 0.3)


class TestSmoothing:
    def test_threshold_counts_sightings_from_any_worker(self):
        from app.ai_monitor import smoothing

        # looking_away needs 2 sightings. Worker process A sees one frame,
        # worker process B the next: shared state means it is confirmed.
        assert smoothing.confirm("att-1", "looking_away") is False   # worker A
        assert smoothing.confirm("att-1", "looking_away") is True    # worker B
        assert smoothing.confirm("att-1", "looking_away") is False   # reset after confirm

    def test_hard_violation_fires_immediately(self):
        from app.ai_monitor import smoothing

        assert smoothing.confirm("att-2", "multiple_faces_detected") is True


# ── Cache stampede ───────────────────────────────────────────────────────────

class TestStampede:
    def test_cold_key_is_computed_once_under_concurrency(self):
        async def main():
            c = RedisCache()
            await c.connect()
            calls = 0

            async def compute():
                nonlocal calls
                calls += 1
                await asyncio.sleep(0.2)       # a slow DB query
                return {"v": 1}

            results = await asyncio.gather(*[
                c.get_or_compute("t:stampede", 30, compute) for _ in range(100)
            ])
            await c.disconnect()
            return calls, results

        calls, results = asyncio.run(main())
        assert calls == 1
        assert all(r == {"v": 1} for r in results)


# ── Auth user cache ──────────────────────────────────────────────────────────

class TestUserCache:
    def test_second_request_skips_users_query(self, client, student_headers, db):
        seen = []

        def count(conn, cursor, statement, params, context, executemany):
            if "FROM users" in statement:
                seen.append(statement)

        bind = db.get_bind()
        event.listen(bind, "before_cursor_execute", count)
        try:
            client.get("/api/v1/auth/me", headers=student_headers)
            first = len(seen)
            client.get("/api/v1/auth/me", headers=student_headers)
            second = len(seen) - first
        finally:
            event.remove(bind, "before_cursor_execute", count)
        assert first == 1
        assert second == 0


# ── Pub/sub fan-out ──────────────────────────────────────────────────────────

class TestPubSub:
    def test_message_published_by_worker_reaches_subscriber(self):
        """A 'Celery worker' (another thread, sync client) publishes; the API
        process's async subscriber receives it."""
        async def main():
            from app.core.cache import cache

            await cache.connect()
            got = asyncio.Queue()
            stop = asyncio.Event()

            async def on_message(m):
                await got.put(m)

            task = asyncio.create_task(events.run_subscriber(on_message, stop))
            await asyncio.sleep(0.3)                   # let it SUBSCRIBE
            threading.Thread(
                target=events.publish_health, args=("att-x", {"current": 90})
            ).start()
            msg = await asyncio.wait_for(got.get(), timeout=3)
            stop.set()
            task.cancel()
            await cache.disconnect()
            return msg

        msg = asyncio.run(main())
        assert msg["attempt_id"] == "att-x"
        assert msg["data"] == {"current": 90}

    def test_manager_delivers_to_every_socket_of_the_attempt(self):
        from app.api.v1.enhanced_monitoring import ConnectionManager

        class FakeWS:
            def __init__(self):
                self.sent = []

            async def accept(self):
                pass

            async def send_json(self, m):
                self.sent.append(m)

        async def main():
            m = ConnectionManager()
            student, examiner, other = FakeWS(), FakeWS(), FakeWS()
            await m.connect("A", student)
            await m.connect("A", examiner)       # used to overwrite the student
            await m.connect("B", other)
            n = await m.dispatch({"attempt_id": "A", "data": {"current": 5},
                                  "alert": {"message": "low"}})
            return n, student, examiner, other

        n, student, examiner, other = asyncio.run(main())
        assert n == 2
        assert [x["type"] for x in student.sent] == ["health_update", "violation_alert"]
        assert examiner.sent == student.sent
        assert other.sent == []


def test_websocket_receives_update_from_another_process(committed_ws):
    """
    End to end: a student's WebSocket is open on the API; a violation is
    recorded by code running outside the request (as a Celery worker would,
    with its own DB session). The update arrives over the socket via Redis.
    """
    from fastapi.testclient import TestClient
    from app.ai_monitor import health
    from app.main import app
    from app.models.attempt import ExamAttempt

    Session, attempt_id, token = committed_ws
    with TestClient(app) as c:
        url = f"/api/v1/monitor/enhanced/ws/proctoring/{attempt_id}?token={token}"
        with c.websocket_connect(url) as ws:
            assert ws.receive_json()["type"] == "connected"
            assert ws.receive_json()["type"] == "health_update"      # snapshot
            time.sleep(0.3)                                           # subscriber ready

            def worker():
                s = Session()
                a = s.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).one()
                health.record_violations(s, a, [{"type": "multiple_faces_detected", "severity": "high"}])
                s.close()

            threading.Thread(target=worker).start()
            msg = ws.receive_json()
            assert msg["type"] == "health_update"
            assert msg["data"]["current"] < 100


@pytest.fixture
def committed_ws(engine):
    import uuid
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker
    from app.core.security import get_password_hash
    from app.models.exam import Exam, ExamStatus
    from app.models.user import User, UserRole
    from app.services.attempt_service import AttemptService
    from tests.conftest import TEST_DB_URL, make_token

    eng = create_engine(TEST_DB_URL)
    Session = sessionmaker(bind=eng)
    s = Session()
    tag = uuid.uuid4().hex[:8]
    ex = User(email=f"wx-{tag}@t.com", password_hash=get_password_hash("x"),
              full_name="E", role=UserRole.EXAMINER, is_verified=True)
    st = User(email=f"ws-{tag}@t.com", password_hash=get_password_hash("x"),
              full_name="S", role=UserRole.STUDENT, is_verified=True)
    s.add_all([ex, st])
    s.commit()
    exam = Exam(title="W", description="", duration_minutes=30, total_marks=1,
                pass_percentage=40, status=ExamStatus.LIVE, created_by=ex.id)
    s.add(exam)
    s.commit()
    attempt = AttemptService(s).start(exam.id, st.id)
    ids = (exam.id, st.id, ex.id, attempt.id)
    token = make_token(st)
    s.close()
    yield Session, str(ids[3]), token
    with eng.begin() as c:
        c.execute(text("DELETE FROM exam_attempts WHERE exam_id = :e"), {"e": ids[0]})
        c.execute(text("DELETE FROM exams WHERE id = :e"), {"e": ids[0]})
        c.execute(text("DELETE FROM users WHERE id IN (:a, :b)"), {"a": ids[1], "b": ids[2]})
    eng.dispose()
