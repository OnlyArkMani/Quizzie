"""
AttemptService — the single owner of an exam attempt's lifecycle.

    start ──► IN_PROGRESS ──save_responses()*──► submit() / deadline / health=0 ──► SUBMITTED ──► EVALUATED

Every state transition out of IN_PROGRESS goes through ``_close_attempt``, a
compare-and-set UPDATE (``... WHERE status = 'IN_PROGRESS'``). Whichever caller
flips the row first wins; everyone else sees ``rowcount == 0`` and knows the
attempt was already closed. That is what makes double-submit, submit-vs-timeout
and submit-vs-health-autosubmit races safe without application-level locks.

Invariants enforced here (and backed by DB constraints in migration 006):
  * at most one IN_PROGRESS attempt per (exam, student)   — partial unique index
  * at most one Response row per (attempt, question)      — unique constraint
  * no answer is accepted after deadline + grace          — server clock only
  * an older auto-save never overwrites a newer answer    — client_seq guard
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.attempt import AttemptStatus, ExamAttempt, Response
from app.models.exam import Exam, ExamStatus
from app.models.question import Question

logger = logging.getLogger(__name__)

# Attempts created before migration 006 have no deadline; keep the old 24 h
# staleness rule for them only.
LEGACY_STALE_AFTER = timedelta(hours=24)


# ── Domain errors (routers map these to HTTP status codes) ────────────────────

class AttemptError(Exception):
    status_code = 400

    def __init__(self, detail: str):
        super().__init__(detail)
        self.detail = detail


class AttemptNotFound(AttemptError):
    status_code = 404


class NotAttemptOwner(AttemptError):
    status_code = 403


class ExamNotLive(AttemptError):
    status_code = 400


class AlreadySubmitted(AttemptError):
    # Kept as 400 + this exact text: the frontend treats it as "already done".
    status_code = 400


class AttemptClosed(AttemptError):
    """Writes rejected because the attempt is over (deadline passed / closed)."""
    status_code = 409


class InvalidAnswer(AttemptError):
    status_code = 422


@dataclass
class AnswerIn:
    question_id: UUID
    selected_option_ids: List[UUID]
    answer_text: Optional[str]
    marked_for_review: bool
    client_seq: int


def _status(attempt: ExamAttempt) -> str:
    s = attempt.status
    return s.value if hasattr(s, "value") else str(s)


class AttemptService:
    def __init__(self, db: Session, now: Optional[datetime] = None):
        self.db = db
        # Injected clock: tests pass a fixed ``now`` instead of sleeping.
        self._now = now

    # ── clock / deadline ──────────────────────────────────────────────────────

    def now(self) -> datetime:
        return self._now or datetime.utcnow()

    @staticmethod
    def grace() -> timedelta:
        return timedelta(seconds=settings.SUBMIT_GRACE_SECONDS)

    def is_expired(self, attempt: ExamAttempt) -> bool:
        """True once the server clock is past deadline + grace."""
        if attempt.deadline is None:
            return attempt.started_at is not None and self.now() - attempt.started_at > LEGACY_STALE_AFTER
        return self.now() > attempt.deadline + self.grace()

    # ── lookups ───────────────────────────────────────────────────────────────

    def _get_owned(self, attempt_id: UUID, student_id, lock: Optional[str] = None) -> ExamAttempt:
        q = self.db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id)
        if lock == "share":
            q = q.with_for_update(read=True)
        elif lock == "update":
            q = q.with_for_update()
        attempt = q.first()
        if attempt is None:
            raise AttemptNotFound("Attempt not found")
        if str(attempt.student_id) != str(student_id):
            raise NotAttemptOwner("Not authorized")
        return attempt

    # ── state transitions ─────────────────────────────────────────────────────

    def _close_attempt(
        self,
        attempt: ExamAttempt,
        submitted_at: datetime,
        idempotency_key: Optional[str] = None,
    ) -> bool:
        """
        Compare-and-set IN_PROGRESS → SUBMITTED. Returns True if THIS call did
        the transition, False if someone else already had. Does not commit.
        """
        started = attempt.started_at or submitted_at
        result = self.db.execute(
            update(ExamAttempt)
            .where(and_(ExamAttempt.id == attempt.id,
                        ExamAttempt.status == AttemptStatus.IN_PROGRESS))
            .values(
                status=AttemptStatus.SUBMITTED,
                submitted_at=submitted_at,
                time_taken_seconds=max(0, int((submitted_at - started).total_seconds())),
                submit_idempotency_key=idempotency_key,
            )
            .execution_options(synchronize_session=False)
        )
        won = result.rowcount == 1
        if won:
            self.db.expire(attempt)   # reload the new status on next access
        return won

    def finalize_if_expired(self, attempt: ExamAttempt) -> bool:
        """
        Lazily close an attempt whose deadline has passed. The recorded
        submission time is the deadline itself, not "whenever someone noticed",
        so time_taken never exceeds the exam duration. Commits.
        """
        if _status(attempt) != AttemptStatus.IN_PROGRESS.value or not self.is_expired(attempt):
            return False
        end = attempt.deadline or self.now()
        closed = self._close_attempt(attempt, submitted_at=end)
        self.db.commit()
        if closed:
            logger.info("Attempt %s auto-finalized at deadline", attempt.id)
            from app.services import evaluation_dispatch
            evaluation_dispatch.dispatch(attempt.id)
        return closed

    # ── start / resume ────────────────────────────────────────────────────────

    def start(self, exam_id: UUID, student_id) -> ExamAttempt:
        exam = self.db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise AttemptNotFound("Exam not found")
        if exam.status != ExamStatus.LIVE:
            raise ExamNotLive("Exam is not live")

        existing = self._active_attempt(exam_id, student_id)
        if existing is not None:
            if not self.finalize_if_expired(existing):
                return existing          # resume

        now = self.now()
        attempt = ExamAttempt(
            exam_id=exam_id,
            student_id=student_id,
            status=AttemptStatus.IN_PROGRESS,
            started_at=now,
            deadline=now + timedelta(minutes=exam.duration_minutes),
        )
        self.db.add(attempt)
        try:
            self.db.commit()
        except IntegrityError:
            # Lost the race: a concurrent /start inserted the active attempt
            # between our SELECT and INSERT. The partial unique index rejected
            # ours, so return the winner — the caller can't tell the difference.
            self.db.rollback()
            winner = self._active_attempt(exam_id, student_id)
            if winner is None:
                raise
            return winner
        self.db.refresh(attempt)
        return attempt

    def _active_attempt(self, exam_id, student_id) -> Optional[ExamAttempt]:
        return (
            self.db.query(ExamAttempt)
            .filter(
                ExamAttempt.exam_id == exam_id,
                ExamAttempt.student_id == student_id,
                ExamAttempt.status == AttemptStatus.IN_PROGRESS,
            )
            .first()
        )

    # ── read model for the exam page (resume after crash / reload) ────────────

    def get_state(self, attempt_id: UUID, student_id) -> Dict:
        attempt = self._get_owned(attempt_id, student_id)
        self.finalize_if_expired(attempt)
        responses = (
            self.db.query(Response).filter(Response.attempt_id == attempt.id).all()
        )
        now = self.now()
        remaining = None
        if attempt.deadline is not None:
            remaining = max(0, int((attempt.deadline - now).total_seconds()))
        return {
            "attempt_id": str(attempt.id),
            "exam_id": str(attempt.exam_id),
            "status": _status(attempt).lower(),
            "started_at": attempt.started_at,
            "deadline": attempt.deadline,
            "server_now": now,
            "remaining_seconds": remaining,
            "responses": [
                {
                    "question_id": str(r.question_id),
                    "selected_option_ids": [str(o) for o in (r.selected_option_ids or [])],
                    "answer_text": r.answer_text,
                    "marked_for_review": bool(r.marked_for_review),
                    "client_seq": int(r.client_seq or 0),
                }
                for r in responses
            ],
        }

    # ── writes ────────────────────────────────────────────────────────────────

    def _validate_questions(self, exam_id, answers: Iterable[AnswerIn]) -> None:
        """Answers may only target questions that belong to this attempt's exam."""
        ids = {a.question_id for a in answers}
        if not ids:
            return
        valid = {
            row[0] for row in self.db.execute(
                select(Question.id).where(Question.exam_id == exam_id, Question.id.in_(ids))
            )
        }
        unknown = ids - valid
        if unknown:
            raise InvalidAnswer(f"{len(unknown)} answer(s) reference questions not in this exam")

    def _upsert(self, attempt_id: UUID, answers: List[AnswerIn]) -> int:
        """
        One round trip, regardless of how many answers:
            INSERT ... VALUES (...), (...)
            ON CONFLICT (attempt_id, question_id) DO UPDATE ...
            WHERE responses.client_seq <= EXCLUDED.client_seq
        Idempotent: replaying the same payload leaves the table unchanged.
        """
        if not answers:
            return 0
        # Last write per question wins within one payload.
        latest: Dict[UUID, AnswerIn] = {}
        for a in answers:
            prev = latest.get(a.question_id)
            if prev is None or a.client_seq >= prev.client_seq:
                latest[a.question_id] = a
        now = self.now()
        rows = [
            {
                "id": uuid.uuid4(),
                "attempt_id": attempt_id,
                "question_id": a.question_id,
                "selected_option_ids": list(a.selected_option_ids),
                "answer_text": a.answer_text,
                "marked_for_review": a.marked_for_review,
                "client_seq": a.client_seq,
                "answered_at": now,
            }
            for a in latest.values()
        ]
        stmt = pg_insert(Response).values(rows)
        excluded = stmt.excluded
        stmt = stmt.on_conflict_do_update(
            constraint="uq_response_attempt_question",
            set_={
                "selected_option_ids": excluded.selected_option_ids,
                "answer_text": excluded.answer_text,
                "marked_for_review": excluded.marked_for_review,
                "client_seq": excluded.client_seq,
                "answered_at": excluded.answered_at,
                # A changed answer invalidates any previous evaluation of it.
                "is_correct": None,
                "marks_awarded": None,
            },
            where=Response.client_seq <= excluded.client_seq,
        )
        self.db.execute(stmt)
        return len(rows)

    def save_responses(self, attempt_id: UUID, student_id, answers: List[AnswerIn]) -> Dict:
        """
        Auto-save. Takes a SHARE lock on the attempt row: many saves for the
        same attempt can proceed together, but none can interleave with the
        exclusive lock that submit's status UPDATE takes. So a save either
        lands fully before the submit or sees the attempt closed — never half.
        """
        attempt = self._get_owned(attempt_id, student_id, lock="share")
        if _status(attempt) != AttemptStatus.IN_PROGRESS.value:
            raise AttemptClosed("Attempt is no longer in progress")
        if self.is_expired(attempt):
            self.finalize_if_expired(attempt)   # upgrades our own share lock
            raise AttemptClosed("Exam time is over")
        self._validate_questions(attempt.exam_id, answers)
        saved = self._upsert(attempt.id, answers)
        self.db.commit()
        return {"saved": saved, "server_now": self.now(), "deadline": attempt.deadline}

    def submit(
        self,
        attempt_id: UUID,
        student_id,
        answers: List[AnswerIn],
        idempotency_key: Optional[str] = None,
    ) -> Tuple[ExamAttempt, Dict]:
        """
        Close the attempt exactly once. Returns (attempt, info) where info has
        ``replay`` (True if this was a retry of an already-applied submit) and
        ``late`` (True if the payload arrived after the deadline and was
        ignored in favour of what was durably saved before it).
        """
        attempt = self._get_owned(attempt_id, student_id)

        if _status(attempt) != AttemptStatus.IN_PROGRESS.value:
            if idempotency_key and attempt.submit_idempotency_key == idempotency_key:
                return attempt, {"replay": True, "late": False}
            raise AlreadySubmitted("Attempt already submitted")

        late = self.is_expired(attempt)
        submitted_at = attempt.deadline if late else self.now()
        if not late:
            self._validate_questions(attempt.exam_id, answers)

        # 1. Status CAS first: it takes the row's exclusive lock for the rest of
        #    this transaction, which fences off concurrent auto-saves (they
        #    need a SHARE lock) until we commit.
        if not self._close_attempt(attempt, submitted_at, idempotency_key):
            self.db.refresh(attempt)
            if idempotency_key and attempt.submit_idempotency_key == idempotency_key:
                return attempt, {"replay": True, "late": False}
            raise AlreadySubmitted("Attempt already submitted")

        # 2. Final answers — only if they arrived in time. A late payload is
        #    dropped; the last auto-save before the deadline is what counts.
        if not late:
            self._upsert(attempt.id, answers)

        self.db.commit()
        self.db.refresh(attempt)
        return attempt, {"replay": False, "late": late}

    # ── used by the proctoring health path (auto-submit on zero health) ──────

    def close_for_health(self, attempt: ExamAttempt) -> bool:
        """Close the attempt because proctoring health hit zero. Does not commit."""
        if _status(attempt) != AttemptStatus.IN_PROGRESS.value:
            return False
        return self._close_attempt(attempt, submitted_at=self.now())
