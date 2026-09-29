"""
Real concurrency tests.

Unlike the rest of the suite (one connection, rolled back per test), these use
COMMITTED data and N threads with N separate connections, so Postgres's actual
locking and constraint enforcement decide the outcome. A threading.Barrier
releases all threads at the same instant to maximise contention.
"""
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.ai_monitor import health
from app.core.security import get_password_hash
from app.models.attempt import AttemptStatus, ExamAttempt, Response
from app.models.exam import Exam, ExamStatus
from app.models.question import Option, Question, QuestionType
from app.models.user import User, UserRole
from app.services.attempt_service import (
    AlreadySubmitted, AnswerIn, AttemptClosed, AttemptService,
)
from tests.conftest import TEST_DB_URL

N = 16


@pytest.fixture
def committed(engine):
    """Committed user/exam/question, deleted afterwards."""
    eng = create_engine(TEST_DB_URL, pool_size=N + 4, max_overflow=0)
    Session = sessionmaker(bind=eng)
    s = Session()
    tag = uuid.uuid4().hex[:8]
    examiner = User(email=f"ex-{tag}@t.com", password_hash=get_password_hash("x"),
                    full_name="Ex", role=UserRole.EXAMINER, is_verified=True)
    student = User(email=f"st-{tag}@t.com", password_hash=get_password_hash("x"),
                   full_name="St", role=UserRole.STUDENT, is_verified=True)
    s.add_all([examiner, student])
    s.commit()
    exam = Exam(title="C", description="", duration_minutes=60, total_marks=10,
                pass_percentage=40, status=ExamStatus.LIVE, created_by=examiner.id)
    s.add(exam)
    s.commit()
    q = Question(exam_id=exam.id, question_text="?", question_type=QuestionType.SINGLE,
                 marks=10, display_order=1)
    s.add(q)
    s.commit()
    opt = Option(question_id=q.id, option_text="a", is_correct=True, display_order=1)
    s.add(opt)
    s.commit()
    ids = dict(exam=exam.id, student=student.id, examiner=examiner.id, q=q.id, opt=opt.id)
    s.close()

    yield Session, ids

    with eng.begin() as c:
        c.execute(text("DELETE FROM exam_attempts WHERE exam_id = :e"), {"e": ids["exam"]})
        c.execute(text("DELETE FROM exams WHERE id = :e"), {"e": ids["exam"]})
        c.execute(text("DELETE FROM users WHERE id IN (:a, :b)"),
                  {"a": ids["student"], "b": ids["examiner"]})
    eng.dispose()


def _race(fn, n=N):
    """Run fn(i) in n threads released simultaneously; return results/exceptions."""
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        try:
            return fn(i)
        except Exception as e:  # collected, not raised
            return e

    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(run, range(n)))


def test_concurrent_start_creates_exactly_one_attempt(committed):
    Session, ids = committed

    def start(_):
        s = Session()
        try:
            return AttemptService(s).start(ids["exam"], ids["student"]).id
        finally:
            s.close()

    results = _race(start)
    assert not [r for r in results if isinstance(r, Exception)], results
    assert len(set(results)) == 1          # every caller got the SAME attempt

    s = Session()
    n = s.query(ExamAttempt).filter(
        ExamAttempt.exam_id == ids["exam"], ExamAttempt.status == AttemptStatus.IN_PROGRESS
    ).count()
    s.close()
    assert n == 1


def test_concurrent_submit_happens_exactly_once(committed):
    Session, ids = committed
    s = Session()
    attempt_id = AttemptService(s).start(ids["exam"], ids["student"]).id
    s.close()
    answer = [AnswerIn(ids["q"], [ids["opt"]], None, False, 1)]

    def submit(i):
        s = Session()
        try:
            _, info = AttemptService(s).submit(attempt_id, ids["student"], answer, f"key-{i}")
            return info
        finally:
            s.close()

    results = _race(submit)
    winners = [r for r in results if isinstance(r, dict) and not r["replay"]]
    losers = [r for r in results if isinstance(r, AlreadySubmitted)]
    assert len(winners) == 1, results
    assert len(losers) == N - 1, results

    s = Session()
    assert s.query(Response).filter(Response.attempt_id == attempt_id).count() == 1
    s.close()


def test_concurrent_submit_retries_with_same_key_all_succeed(committed):
    """A client retrying one logical submit N times sees N successes, 1 effect."""
    Session, ids = committed
    s = Session()
    attempt_id = AttemptService(s).start(ids["exam"], ids["student"]).id
    s.close()

    def submit(_):
        s = Session()
        try:
            return AttemptService(s).submit(attempt_id, ids["student"], [], "same-key")[1]
        finally:
            s.close()

    results = _race(submit)
    assert all(isinstance(r, dict) for r in results), results
    assert sum(1 for r in results if not r["replay"]) == 1


def test_autosave_never_lands_after_submit(committed, monkeypatch):
    """
    Auto-saves racing a submit either commit before it (and are part of the
    submission) or are rejected with AttemptClosed. Nothing may change the
    attempt's answers after the submit has committed.

    How that's checked: the submitting thread reads the answer row right after
    its commit returns; after every thread has finished, the row must be
    unchanged. (Comparing answered_at with submitted_at would NOT prove it:
    a timestamp is taken when a statement runs, not when it commits — an
    auto-save stamped after the submit's timestamp can still have committed
    first, because the submit's UPDATE waited on the auto-save's lock.)
    """
    Session, ids = committed
    s = Session()
    attempt_id = AttemptService(s).start(ids["exam"], ids["student"]).id
    s.close()

    # Widen the race window: pause each auto-save between its status check and
    # its write. With the SHARE lock the submit simply waits; without it the
    # submit commits during the pause and the save lands afterwards — this
    # test fails reliably if the lock is removed (verified by mutation).
    import time as _time
    original_validate = AttemptService._validate_questions

    def slow_validate(self, exam_id, answers):
        if answers:                      # auto-saves only; the submit sends []
            _time.sleep(0.05)
            # Stamp the edit AFTER the pause with a strictly newer seq, so a save
            # that lands late would visibly overwrite the row (an older seq would
            # be ignored by the client_seq guard and hide the bug).
            for a in answers:
                a.client_seq = _time.monotonic_ns()
        return original_validate(self, exam_id, answers)

    monkeypatch.setattr(AttemptService, "_validate_questions", slow_validate)

    def answer_seq():
        s = Session()
        try:
            r = s.query(Response).filter(Response.attempt_id == attempt_id).first()
            return None if r is None else r.client_seq
        finally:
            s.close()

    def work(i):
        s = Session()
        try:
            svc = AttemptService(s)
            if i == N // 2:
                svc.submit(attempt_id, ids["student"], [], "k")
                return ("submitted", answer_seq())
            svc.save_responses(attempt_id, ids["student"],
                               [AnswerIn(ids["q"], [ids["opt"]], None, False, i)])
            return "saved"
        finally:
            s.close()

    results = _race(work)
    submitted = [r for r in results if isinstance(r, tuple)]
    assert len(submitted) == 1, results
    others = [r for r in results if not isinstance(r, tuple)]
    assert all(r == "saved" or isinstance(r, AttemptClosed) for r in others), results

    seq_at_submit = submitted[0][1]
    assert answer_seq() == seq_at_submit      # frozen from the moment submit committed


def test_concurrent_violations_lose_no_penalty(committed, monkeypatch):
    """
    N workers each apply a 'looking_away' penalty to the same attempt at once.
    With the old read-modify-write, several read the same starting health and
    penalties were lost. With the atomic UPDATE the total is exact.
    """
    from app.ai_monitor import scoring

    Session, ids = committed
    s = Session()
    attempt_id = AttemptService(s).start(ids["exam"], ids["student"]).id
    s.close()
    penalty = scoring.health_penalty("looking_away", "medium")
    n = min(N, 100 // penalty - 1)    # stay above zero so nothing is clamped

    def violate(_):
        s = Session()
        try:
            a = s.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).one()
            health.record_violations(s, a, [{"type": "looking_away", "severity": "medium"}])
        finally:
            s.close()

    results = _race(violate, n)
    assert not [r for r in results if isinstance(r, Exception)], results

    s = Session()
    a = s.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).one()
    s.close()
    assert a.current_health == 100 - n * penalty
    assert a.cheating_flags == n
