"""
Attempts API — start/resume, durable auto-save, submit, results, grading.

The routes are thin: the attempt lifecycle (and its concurrency rules) lives in
``app.services.attempt_service.AttemptService``.

Submit flow
-----------
1. AttemptService.submit: compare-and-set the status to SUBMITTED and upsert the
   final answers in ONE transaction (exactly-once, even under concurrent calls).
2. Try to dispatch the Celery evaluation task (async, best-effort, 5 s cap).
3. If Celery/Redis is unavailable, evaluate synchronously in-process instead.
"""
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import logging

from app.core.database import get_db, run_db
from app.core.cache import cache, key_leaderboard
from app.models.user import User
from app.models.exam import Exam
from app.models.attempt import ExamAttempt, Response, AttemptStatus
from app.models.question import Question
from app.schemas.response import (
    AttemptCreate, AttemptSubmit, AutoSaveRequest, Attempt as AttemptSchema, GradeRequest,
)
from app.api.deps import get_current_user, require_role
from app.services.evaluation_service import EvaluationService
from app.services.attempt_service import AnswerIn, AttemptError, AttemptService
from app.services import evaluation_dispatch

logger = logging.getLogger(__name__)

# ── Celery task import (optional — app works without it) ─────────────────────
# We import at module level so tests can patch it via:
#   patch("app.api.v1.attempts.evaluate_attempt_task")
# If Celery/Redis is not available the import still succeeds (Celery is lazy);
# the task only fails when .apply_async() is called.
try:
    from app.worker.tasks.evaluation_tasks import evaluate_attempt_task as _celery_task
except Exception:
    _celery_task = None

evaluate_attempt_task = _celery_task

router = APIRouter()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _try_celery(attempt_id: str) -> tuple[bool, dict | None]:
    """
    Try to dispatch the evaluation task to Celery.
    Returns (dispatched: bool, task_info: dict | None).

    We wrap this in a tight try/except so ANY Celery/Redis error
    (connection refused, timeout, WinError 5, etc.) falls back instantly
    to synchronous evaluation instead of hanging the request.
    """
    import app.api.v1.attempts as _mod  # always read current binding for test patching
    task_id = evaluation_dispatch.enqueue(_mod.evaluate_attempt_task, attempt_id)
    return (True, {"task_id": task_id}) if task_id else (False, None)


# ── Routes ────────────────────────────────────────────────────────────────────
#
# Student hot-path routes are ``async def`` and do ALL their DB work inside one
# ``run_db`` call (see app.core.database.run_db): blocking work never runs on
# the event loop, and the transaction/connection is released before the worker
# thread is. Low-traffic examiner routes stay plain ``def``.

def _answers(items) -> List[AnswerIn]:
    return [
        AnswerIn(
            question_id=r.question_id,
            selected_option_ids=list(r.selected_option_ids or []),
            answer_text=r.answer_text,
            marked_for_review=r.marked_for_review,
            client_seq=r.client_seq,
        )
        for r in items
    ]


def _raise_http(e: AttemptError):
    raise HTTPException(status_code=e.status_code, detail=e.detail)


def _service_call(db: Session, method: str, *args):
    """Run an AttemptService method; map domain errors to HTTP (in the worker)."""
    try:
        return getattr(AttemptService(db), method)(*args)
    except AttemptError as e:
        _raise_http(e)


def _attempt_dto(attempt: ExamAttempt) -> dict:
    return AttemptSchema.model_validate(attempt).model_dump()


@router.post("/start", response_model=AttemptSchema, status_code=status.HTTP_201_CREATED)
async def start_exam(
    attempt_data: AttemptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """Start a new attempt or resume the active one. Safe to call repeatedly."""
    return await run_db(
        db, lambda: _attempt_dto(_service_call(db, "start", attempt_data.exam_id, current_user.id))
    )


@router.get("/{attempt_id}/state")
async def get_attempt_state(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Everything the exam page needs to (re)hydrate after a reload or crash:
    saved answers, the server-side deadline and the server's current time
    (the client derives its countdown from these, never from its own clock).
    """
    return await run_db(db, _service_call, db, "get_state", attempt_id, current_user.id)


@router.post("/{attempt_id}/auto-save", status_code=200)
async def auto_save_progress(
    attempt_id: UUID,
    body: AutoSaveRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Durable, idempotent delta save. Upserts on (attempt_id, question_id);
    replaying the same payload is a no-op, and an out-of-order (older
    client_seq) save cannot overwrite a newer answer.
    """
    result = await run_db(
        db, _service_call, db, "save_responses", attempt_id, current_user.id, _answers(body.responses)
    )
    return {"message": "Progress saved", **result}


def _submit_blocking(db: Session, attempt_id: UUID, student_id, answers, idem_key):
    """Everything in submit that blocks: DB transaction + evaluation dispatch."""
    svc = AttemptService(db)
    attempt, info = svc.submit(attempt_id, student_id, answers, idem_key)
    exam_id = str(attempt.exam_id)

    if info["replay"]:
        body = {
            "message": "Exam already submitted (idempotent replay).",
            "attempt_id": str(attempt_id),
            "status": attempt.status.value.lower() if hasattr(attempt.status, "value") else str(attempt.status),
            "idempotent_replay": True,
        }
        return exam_id, body

    base = {"attempt_id": str(attempt_id), "late": info["late"], "idempotent_replay": False}

    dispatched, task_info = _try_celery(str(attempt_id))
    if dispatched:
        return exam_id, {
            "message": "Exam submitted successfully. Results will be ready shortly.",
            "task_id": task_info["task_id"],
            "status": "evaluating",
            **base,
        }

    logger.info("Evaluating attempt %s synchronously (Celery unavailable).", attempt_id)
    result = EvaluationService(db).evaluate_attempt(attempt_id)
    return exam_id, {
        "message": "Exam submitted and evaluated successfully.",
        "status": "evaluated",
        **base,
        **result,
    }


@router.post("/{attempt_id}/submit", response_model=dict)
async def submit_exam(
    attempt_id: UUID,
    submission: AttemptSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"])),
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key", max_length=64),
):
    """
    Submit exactly once. Concurrency-safe via a compare-and-set status UPDATE;
    a retry carrying the same Idempotency-Key gets a success replay instead of
    an error. After deadline + grace the payload is ignored and the attempt is
    closed with the answers that were auto-saved in time.
    """
    try:
        exam_id, body = await run_db(
            db, _submit_blocking, db, attempt_id, current_user.id,
            _answers(submission.responses), idempotency_key,
        )
    except AttemptError as e:
        _raise_http(e)

    if not body.get("idempotent_replay"):
        await cache.delete(key_leaderboard(exam_id))
    return body


@router.get("/{attempt_id}/results", response_model=dict)
async def get_results(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Final results, or ``202 {"status": "evaluating"}`` while a queued
    evaluation is still pending — the client polls. The results page no
    longer runs the evaluation on every poll.
    """
    body = await run_db(db, _results_blocking, db, attempt_id, current_user)
    if body.get("status") == "evaluating":
        return JSONResponse(status_code=202, content=body, headers={"Retry-After": "2"})
    return body


def _results_blocking(db: Session, attempt_id: UUID, current_user: User) -> dict:
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    if role == "student" and str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    elif role == "examiner" and str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    # An attempt whose deadline passed is closed lazily on first touch.
    AttemptService(db).finalize_if_expired(attempt)

    status_val = attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status)

    if status_val == AttemptStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=400, detail="Exam not yet submitted")

    if status_val == AttemptStatus.SUBMITTED.value:
        # A queued evaluation is on its way: tell the client to poll.
        if evaluation_dispatch.is_pending(attempt_id):
            return {"status": "evaluating", "attempt_id": str(attempt_id)}
        # Nothing queued (Celery down, or the task died and its marker expired):
        # evaluate inline — but only one concurrent poller does it.
        if not evaluation_dispatch.acquire_inline_lock(attempt_id):
            return {"status": "evaluating", "attempt_id": str(attempt_id)}
        try:
            EvaluationService(db).evaluate_attempt(attempt_id)
        finally:
            evaluation_dispatch.release_inline_lock(attempt_id)
        db.refresh(attempt)
        status_val = AttemptStatus.EVALUATED.value

    # Should be EVALUATED now
    responses = db.query(Response).filter(Response.attempt_id == attempt_id).all()

    score = float(attempt.score) if attempt.score is not None else 0.0
    obtained_marks = sum(
        float(r.marks_awarded) for r in responses if r.marks_awarded is not None
    )

    # Count coding/subjective answers still awaiting examiner grading so the
    # results screen can show "pending grading" instead of a misleading final %.
    from app.models.question import MANUAL_QUESTION_TYPES
    q_map = {
        q.id: q for q in db.query(Question).filter(
            Question.id.in_([r.question_id for r in responses] or [None])
        ).all()
    }

    def _qt(q):
        return q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type)

    pending_grading = sum(
        1 for r in responses
        if (q := q_map.get(r.question_id)) is not None
        and _qt(q) in MANUAL_QUESTION_TYPES
        and r.marks_awarded is None
    )

    topic_wise: dict = {}
    for r in responses:
        q = q_map.get(r.question_id)
        if q and q.topic:
            if q.topic not in topic_wise:
                topic_wise[q.topic] = {"correct": 0, "total": 0, "percentage": 0.0}
            topic_wise[q.topic]["total"] += 1
            if r.is_correct:
                topic_wise[q.topic]["correct"] += 1

    # Compute percentages
    for t in topic_wise.values():
        t["percentage"] = round((t["correct"] / t["total"]) * 100, 1) if t["total"] else 0.0

    return {
        "status": "evaluated",
        "score": score,
        "obtained_marks": obtained_marks,
        "total_marks": float(exam.total_marks),
        "correct_count": sum(1 for r in responses if r.is_correct),
        "total_questions": len(responses),
        "time_taken_seconds": attempt.time_taken_seconds,
        "cheating_flags": attempt.cheating_flags or 0,
        "pass_percentage": float(exam.pass_percentage),
        "needs_grading": pending_grading > 0,
        "pending_grading": pending_grading,
        "topic_wise": topic_wise,
    }


@router.get("/my-attempts", response_model=List[AttemptSchema])
async def get_my_attempts(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    def work():
        rows = (
            db.query(ExamAttempt)
            .filter(ExamAttempt.student_id == current_user.id)
            .order_by(ExamAttempt.started_at.desc())
            .limit(min(limit, 100))
            .all()
        )
        return [_attempt_dto(a) for a in rows]

    return await run_db(db, work)


# ── Manual grading (coding / subjective) ────────────────────────────────────────

def _require_exam_owner(db: Session, attempt: ExamAttempt, current_user: User) -> Exam:
    """Ensure the caller is the examiner who owns this attempt's exam (or admin)."""
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role not in ("examiner", "admin"):
        raise HTTPException(status_code=403, detail="Examiners only")
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if role == "examiner" and str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to grade this exam")
    return exam


@router.get("/{attempt_id}/grading")
def get_grading_queue(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List the coding/subjective answers in an attempt that an examiner grades."""
    from app.models.question import MANUAL_QUESTION_TYPES

    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    _require_exam_owner(db, attempt, current_user)

    responses = db.query(Response).filter(Response.attempt_id == attempt_id).all()
    q_map = {
        q.id: q for q in db.query(Question).filter(
            Question.id.in_([r.question_id for r in responses] or [None])
        ).all()
    }

    def _qt(q):
        return q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type)

    items = []
    for r in responses:
        q = q_map.get(r.question_id)
        if not q or _qt(q) not in MANUAL_QUESTION_TYPES:
            continue
        items.append({
            "response_id": str(r.id),
            "question_id": str(q.id),
            "question_text": q.question_text,
            "question_type": _qt(q),
            "language": q.language,
            "reference_answer": q.reference_answer,
            "max_marks": q.marks,
            "answer_text": r.answer_text or "",
            "marks_awarded": float(r.marks_awarded) if r.marks_awarded is not None else None,
        })

    return {
        "attempt_id": str(attempt_id),
        "items": items,
        "pending": sum(1 for it in items if it["marks_awarded"] is None),
    }


@router.post("/{attempt_id}/grade")
def grade_attempt(
    attempt_id: UUID,
    body: GradeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Set examiner marks for coding/subjective responses, then recompute the
    attempt's overall score from all graded marks.
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    _require_exam_owner(db, attempt, current_user)

    responses = {r.id: r for r in db.query(Response).filter(Response.attempt_id == attempt_id).all()}
    q_map = {q.id: q for q in db.query(Question).filter(
        Question.id.in_([r.question_id for r in responses.values()] or [None])
    ).all()}

    for item in body.grades:
        r = responses.get(item.response_id)
        if not r:
            raise HTTPException(status_code=404, detail=f"Response {item.response_id} not found")
        q = q_map.get(r.question_id)
        max_marks = q.marks if q else 0
        if item.marks_awarded < 0 or item.marks_awarded > max_marks:
            raise HTTPException(
                status_code=400,
                detail=f"Marks must be between 0 and {max_marks} for response {item.response_id}"
            )
        r.marks_awarded = item.marks_awarded

    # Recompute overall score across all responses.
    all_responses = list(responses.values())
    total_marks = sum((q_map[r.question_id].marks for r in all_responses if r.question_id in q_map), 0)
    obtained = sum(float(r.marks_awarded) for r in all_responses if r.marks_awarded is not None)
    attempt.score = (obtained / total_marks * 100) if total_marks > 0 else 0
    attempt.status = AttemptStatus.EVALUATED

    db.commit()

    def _qt(q):
        return q.question_type.value if hasattr(q.question_type, "value") else str(q.question_type)

    from app.models.question import MANUAL_QUESTION_TYPES
    pending = sum(
        1 for r in all_responses
        if r.question_id in q_map and _qt(q_map[r.question_id]) in MANUAL_QUESTION_TYPES
        and r.marks_awarded is None
    )

    return {
        "attempt_id": str(attempt_id),
        "score": float(attempt.score),
        "obtained_marks": obtained,
        "total_marks": total_marks,
        "pending_grading": pending,
    }
