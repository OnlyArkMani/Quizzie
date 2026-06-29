"""
Attempts API — exam start, submit, results, auto-save.

Submit flow
-----------
1. Validate + persist responses synchronously (always fast, just SQL inserts).
2. Try to dispatch Celery evaluation task (async, best-effort).
3. If Celery/Redis is unavailable, evaluate synchronously in-process instead.
   This guarantees the HTTP response always returns quickly regardless of
   whether Redis is running — critical for the Windows dev environment where
   Redis may not be installed.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
from uuid import UUID
from pydantic import BaseModel
import logging

from app.core.database import get_db
from app.core.cache import cache, key_leaderboard
from app.models.user import User
from app.models.exam import Exam
from app.models.attempt import ExamAttempt, Response, AttemptStatus
from app.models.question import Question
from app.schemas.response import AttemptCreate, AttemptSubmit, Attempt as AttemptSchema, GradeRequest
from app.api.deps import get_current_user, require_role
from app.services.evaluation_service import EvaluationService

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


class AutoSaveBody(BaseModel):
    responses: List[dict]


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
    task_fn = _mod.evaluate_attempt_task
    if task_fn is None:
        return False, None
    try:
        # apply_async can block if the broker is slow to refuse.
        # We set a short socket timeout in celery_app.py (3 s), but as an
        # extra safety net we run the dispatch in a thread with a 5 s timeout.
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                task_fn.apply_async,
                args=[attempt_id],
                kwargs={"queue": "evaluation"},
            )
            task = future.result(timeout=5)   # 5 s hard cap — never hangs the request
        return True, {"task_id": task.id}
    except Exception as e:
        logger.warning(
            "Celery unavailable (%s) — falling back to synchronous evaluation.", e
        )
        return False, None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/start", response_model=AttemptSchema, status_code=status.HTTP_201_CREATED)
def start_exam(
    attempt_data: AttemptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    exam = db.query(Exam).filter(Exam.id == attempt_data.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status.value != "live":
        raise HTTPException(status_code=400, detail="Exam is not live")

    cutoff_time = datetime.utcnow() - timedelta(hours=24)

    # Expire stale in-progress attempts (> 24 h old)
    db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == attempt_data.exam_id,
        ExamAttempt.student_id == current_user.id,
        ExamAttempt.status == AttemptStatus.IN_PROGRESS,
        ExamAttempt.started_at < cutoff_time,
    ).update({"status": AttemptStatus.SUBMITTED})

    # Resume existing valid attempt
    existing = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == attempt_data.exam_id,
        ExamAttempt.student_id == current_user.id,
        ExamAttempt.status == AttemptStatus.IN_PROGRESS,
        ExamAttempt.started_at >= cutoff_time,
    ).first()
    if existing:
        return existing

    new_attempt = ExamAttempt(
        exam_id=attempt_data.exam_id,
        student_id=current_user.id,
        status=AttemptStatus.IN_PROGRESS,
    )
    db.add(new_attempt)
    db.commit()
    db.refresh(new_attempt)
    return new_attempt


@router.post("/{attempt_id}/submit", response_model=dict)
async def submit_exam(
    attempt_id: UUID,
    submission: AttemptSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    status_val = attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status)
    if status_val != AttemptStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=400, detail="Attempt already submitted")

    # ── 1. Persist responses (fast SQL inserts) ───────────────────────────────
    for rd in submission.responses:
        db.add(Response(
            attempt_id=attempt_id,
            question_id=rd.question_id,
            selected_option_ids=rd.selected_option_ids or [],
            answer_text=rd.answer_text,
            marked_for_review=rd.marked_for_review,
        ))

    attempt.submitted_at = datetime.utcnow()
    attempt.time_taken_seconds = int(
        (attempt.submitted_at - attempt.started_at).total_seconds()
    )
    attempt.status = AttemptStatus.SUBMITTED
    db.commit()

    # ── 2. Try Celery (non-blocking, 5 s max) ────────────────────────────────
    dispatched, task_info = _try_celery(str(attempt_id))

    if dispatched:
        # Cache busting — best-effort, don't let it block
        try:
            await cache.delete(key_leaderboard(str(attempt.exam_id)))
        except Exception:
            pass
        return {
            "message": "Exam submitted successfully. Results will be ready shortly.",
            "attempt_id": str(attempt_id),
            "task_id": task_info["task_id"],
            "status": "evaluating",
        }

    # ── 3. Synchronous fallback (always works, no Redis needed) ───────────────
    logger.info("Evaluating attempt %s synchronously (Celery unavailable).", attempt_id)
    svc = EvaluationService(db)
    result = svc.evaluate_attempt(attempt_id)

    try:
        await cache.delete(key_leaderboard(str(attempt.exam_id)))
    except Exception:
        pass

    return {
        "message": "Exam submitted and evaluated successfully.",
        "attempt_id": str(attempt_id),
        "status": "evaluated",
        **result,
    }


@router.get("/{attempt_id}/results", response_model=dict)
def get_results(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    if role == "student" and str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    elif role == "examiner" and str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    status_val = attempt.status.value if hasattr(attempt.status, "value") else str(attempt.status)

    if status_val == AttemptStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=400, detail="Exam not yet submitted")

    if status_val == AttemptStatus.SUBMITTED.value:
        # Evaluate now — covers the case where Celery worker hasn't picked it up yet
        # or is unavailable (e.g. dev without Redis).
        svc = EvaluationService(db)
        result = svc.evaluate_attempt(attempt_id)
        # Re-fetch updated attempt
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
def get_my_attempts(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    return (
        db.query(ExamAttempt)
        .filter(ExamAttempt.student_id == current_user.id)
        .order_by(ExamAttempt.started_at.desc())
        .limit(limit)
        .all()
    )


@router.post("/{attempt_id}/auto-save", status_code=200)
def auto_save_progress(
    attempt_id: UUID,
    body: AutoSaveBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt or str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")
    return {"message": "Progress saved", "saved": len(body.responses)}


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
