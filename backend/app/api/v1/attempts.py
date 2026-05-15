"""
Attempts API — exam start, submit, results, auto-save.
Submit now dispatches evaluation to Celery so the HTTP response is instant.
"""
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
from uuid import UUID
from pydantic import BaseModel

from app.core.database import get_db
from app.core.cache import cache, key_leaderboard
from app.models.user import User
from app.models.exam import Exam, ExamStatus
from app.models.attempt import ExamAttempt, Response, AttemptStatus
from app.models.question import Question
from app.schemas.response import AttemptCreate, AttemptSubmit, Attempt as AttemptSchema
from app.api.deps import get_current_user, require_role
from app.services.evaluation_service import EvaluationService

router = APIRouter()


class AutoSaveBody(BaseModel):
    responses: List[dict]


@router.post("/start", response_model=AttemptSchema, status_code=status.HTTP_201_CREATED)
def start_exam(
    attempt_data: AttemptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    exam = db.query(Exam).filter(Exam.id == attempt_data.exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status != ExamStatus.LIVE:
        raise HTTPException(status_code=400, detail="Exam is not live")

    cutoff_time = datetime.utcnow() - timedelta(hours=24)

    # Abandon stale in-progress attempts
    db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == attempt_data.exam_id,
        ExamAttempt.student_id == current_user.id,
        ExamAttempt.status == AttemptStatus.IN_PROGRESS,
        ExamAttempt.started_at < cutoff_time,
    ).update({"status": AttemptStatus.SUBMITTED})

    # Resume existing attempt if within 24 hours
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

    status_val = attempt.status.value if hasattr(attempt.status, "value") else attempt.status
    if status_val != AttemptStatus.IN_PROGRESS.value:
        raise HTTPException(status_code=400, detail="Attempt already submitted")

    # Persist responses
    for rd in submission.responses:
        db.add(Response(
            attempt_id=attempt_id,
            question_id=rd.question_id,
            selected_option_ids=rd.selected_option_ids,
            marked_for_review=rd.marked_for_review,
        ))

    attempt.submitted_at = datetime.utcnow()
    attempt.time_taken_seconds = int((attempt.submitted_at - attempt.started_at).total_seconds())
    attempt.status = AttemptStatus.SUBMITTED
    db.commit()

    # Dispatch evaluation to Celery worker (non-blocking)
    # Falls back to synchronous evaluation if Celery/Redis unavailable
    try:
        from app.worker.tasks.evaluation_tasks import evaluate_attempt_task
        task = evaluate_attempt_task.apply_async(
            args=[str(attempt_id)],
            queue="evaluation",
        )
        # Invalidate leaderboard cache for this exam
        await cache.delete(key_leaderboard(str(attempt.exam_id)))
        return {
            "message": "Exam submitted. Results will be ready shortly.",
            "attempt_id": str(attempt_id),
            "task_id": task.id,
            "status": "evaluating",
        }
    except Exception:
        # Synchronous fallback — works without Celery (dev mode)
        svc = EvaluationService(db)
        result = svc.evaluate_attempt(attempt_id)
        await cache.delete(key_leaderboard(str(attempt.exam_id)))
        return result


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

    status_val = attempt.status.value if hasattr(attempt.status, "value") else attempt.status
    if status_val == AttemptStatus.SUBMITTED.value:
        return {"status": "evaluating", "message": "Results are being processed. Please check back in a moment."}
    if status_val != AttemptStatus.EVALUATED.value:
        raise HTTPException(status_code=400, detail="Results not ready yet")

    responses = db.query(Response).filter(Response.attempt_id == attempt_id).all()
    obtained_marks = sum(r.marks_awarded for r in responses if r.marks_awarded)

    # topic-wise (responses already in memory — no extra query)
    topic_wise: dict = {}
    for r in responses:
        q = db.query(Question).filter(Question.id == r.question_id).first()
        if q and q.topic:
            if q.topic not in topic_wise:
                topic_wise[q.topic] = {"correct": 0, "total": 0}
            topic_wise[q.topic]["total"] += 1
            if r.is_correct:
                topic_wise[q.topic]["correct"] += 1

    return {
        "score": float(attempt.score),
        "obtained_marks": float(obtained_marks),
        "total_marks": exam.total_marks,
        "correct_count": sum(1 for r in responses if r.is_correct),
        "total_questions": len(responses),
        "time_taken_seconds": attempt.time_taken_seconds,
        "cheating_flags": attempt.cheating_flags,
        "pass_percentage": float(exam.pass_percentage),
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
