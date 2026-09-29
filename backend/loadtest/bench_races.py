"""
Race-condition benchmark: run the SAME concurrent scenarios against whichever
version of the code is on PYTHONPATH (the pre-upgrade code or this one) and
count anomalies. Uses committed data and N real threads/connections.

    DATABASE_URL=... python -m loadtest.bench_races --trials 20 --threads 16

Scenarios
  start   N simultaneous "Start exam" clicks  -> expect 1 active attempt
  submit  N simultaneous submits of 1 attempt -> expect 1 success, 1 row/question
  health  N simultaneous violations (penalty p each) -> expect 100 - N*p

Pre-upgrade code is driven through its route functions (start_exam,
submit_exam, record_violations) since it has no service layer.
"""
import argparse
import asyncio
import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

from sqlalchemy import text

from app.core.database import Base, SessionLocal, engine
import app.models  # noqa: F401
from app.models.attempt import AttemptStatus, ExamAttempt, Response
from app.models.exam import Exam, ExamStatus
from app.models.question import Option, Question, QuestionType
from app.models.user import User, UserRole

try:
    from app.services.attempt_service import AttemptService, AnswerIn  # upgraded code
    NEW = True
except ImportError:
    NEW = False


def race(fn, n):
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        try:
            return fn(i)
        except Exception as e:
            return e

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))


def fixture():
    s = SessionLocal()
    tag = uuid.uuid4().hex[:8]
    ex = User(email=f"rx-{tag}@b.com", password_hash="x", full_name="E",
              role=UserRole.EXAMINER, is_verified=True)
    st = User(email=f"rs-{tag}@b.com", password_hash="x", full_name="S",
              role=UserRole.STUDENT, is_verified=True)
    s.add_all([ex, st])
    s.commit()
    exam = Exam(title="R", description="", duration_minutes=60, total_marks=1,
                pass_percentage=40, status=ExamStatus.LIVE, created_by=ex.id)
    s.add(exam)
    s.commit()
    q = Question(exam_id=exam.id, question_text="?", question_type=QuestionType.SINGLE,
                 marks=1, display_order=1)
    s.add(q)
    s.commit()
    o = Option(question_id=q.id, option_text="a", is_correct=True, display_order=1)
    s.add(o)
    s.commit()
    ids = (exam.id, st.id, q.id, o.id)
    s.close()
    return ids


def get_user(s, uid):
    return s.query(User).filter(User.id == uid).one()


# ── scenarios ────────────────────────────────────────────────────────────────

def start_once(exam_id, uid):
    s = SessionLocal()
    try:
        if NEW:
            return AttemptService(s).start(exam_id, uid).id
        from app.api.v1.attempts import start_exam
        from app.schemas.response import AttemptCreate
        return start_exam(AttemptCreate(exam_id=exam_id), db=s, current_user=get_user(s, uid)).id
    finally:
        s.close()


def scenario_start(n):
    exam_id, uid, _, _ = fixture()
    res = race(lambda i: start_once(exam_id, uid), n)
    s = SessionLocal()
    active = s.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam_id, ExamAttempt.status == AttemptStatus.IN_PROGRESS).count()
    s.close()
    errors = sum(isinstance(r, Exception) for r in res)
    return {"active_attempts": active, "errors": errors, "anomaly": active != 1 or errors > 0}


def scenario_submit(n):
    exam_id, uid, qid, oid = fixture()
    attempt_id = start_once(exam_id, uid)
    no_celery = MagicMock()
    no_celery.apply_async.side_effect = Exception("no broker")

    def submit(i):
        s = SessionLocal()
        try:
            if NEW:
                AttemptService(s).submit(attempt_id, uid, [AnswerIn(qid, [oid], None, False, 1)], f"k{i}")
                return "ok"
            from app.api.v1.attempts import submit_exam
            from app.schemas.response import AttemptSubmit
            body = AttemptSubmit(responses=[{"question_id": str(qid), "selected_option_ids": [str(oid)]}])
            with patch("app.api.v1.attempts.evaluate_attempt_task", no_celery):
                asyncio.run(submit_exam(attempt_id, body, db=s, current_user=get_user(s, uid)))
            return "ok"
        finally:
            s.close()

    res = race(submit, n)
    s = SessionLocal()
    rows = s.query(Response).filter(Response.attempt_id == attempt_id).count()
    s.close()
    ok = sum(r == "ok" for r in res)
    return {"successful_submits": ok, "response_rows": rows, "anomaly": ok != 1 or rows != 1}


def scenario_health(n):
    from app.ai_monitor import health, scoring

    exam_id, uid, _, _ = fixture()
    attempt_id = start_once(exam_id, uid)
    penalty = scoring.health_penalty("looking_away", "medium")
    n = min(n, 100 // penalty - 1)

    def violate(i):
        s = SessionLocal()
        try:
            a = s.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).one()
            health.record_violations(s, a, [{"type": "looking_away", "severity": "medium"}])
        finally:
            s.close()

    race(violate, n)
    s = SessionLocal()
    a = s.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).one()
    s.close()
    expected = 100 - n * penalty
    lost = (a.current_health - expected) // penalty
    return {"expected_health": expected, "actual_health": a.current_health,
            "lost_penalties": lost, "anomaly": lost != 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=20)
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    Base.metadata.create_all(bind=engine)

    report = {"code": "upgraded" if NEW else "pre-upgrade", "trials": a.trials, "threads": a.threads}
    for name, fn in [("start", scenario_start), ("submit", scenario_submit), ("health", scenario_health)]:
        runs = [fn(a.threads) for _ in range(a.trials)]
        report[name] = {
            "trials_with_anomaly": sum(r["anomaly"] for r in runs),
            "example_bad_trial": next((r for r in runs if r["anomaly"]), None),
        }
        if name == "health":
            report[name]["total_lost_penalties"] = sum(r["lost_penalties"] for r in runs)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
