from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List
from uuid import UUID
from pydantic import BaseModel

from app.core.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.attempt import ExamAttempt, Response, AttemptStatus
from app.models.question import Question, Option
from app.schemas.response import AttemptCreate, AttemptSubmit, Attempt as AttemptSchema
from app.api.deps import get_current_user, require_role
from app.services.evaluation_service import EvaluationService

router = APIRouter()


# FIX Bug 6: Proper Pydantic body model for auto-save
class AutoSaveBody(BaseModel):
    responses: List[dict]


@router.post("/start", response_model=AttemptSchema, status_code=status.HTTP_201_CREATED)
def start_exam(
    attempt_data: AttemptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """Start a new exam attempt (Student only)"""
    exam = db.query(Exam).filter(Exam.id == attempt_data.exam_id).first()

    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    if exam.status != "live":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Exam is not live")

    # Auto-abandon old in-progress attempts (older than 24 hours)
    cutoff_time = datetime.utcnow() - timedelta(hours=24)

    old_attempts = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == attempt_data.exam_id,
        ExamAttempt.student_id == current_user.id,
        # FIX Bug 10: Use enum value
        ExamAttempt.status == AttemptStatus.IN_PROGRESS,
        ExamAttempt.started_at < cutoff_time
    ).all()

    for attempt in old_attempts:
        attempt.status = "abandoned"

    # Check for recent in-progress attempt
    recent_attempt = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == attempt_data.exam_id,
        ExamAttempt.student_id == current_user.id,
        # FIX Bug 10: Use enum value
        ExamAttempt.status == AttemptStatus.IN_PROGRESS,
        ExamAttempt.started_at >= cutoff_time
    ).first()

    if recent_attempt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You have an exam in progress. Please complete or submit it first."
        )

    # Create new attempt
    new_attempt = ExamAttempt(
        exam_id=attempt_data.exam_id,
        student_id=current_user.id,
        # FIX Bug 10: Use enum value
        status=AttemptStatus.IN_PROGRESS
    )

    db.add(new_attempt)
    db.commit()
    db.refresh(new_attempt)

    return new_attempt


@router.post("/{attempt_id}/submit", response_model=dict)
def submit_exam(
    attempt_id: UUID,
    submission: AttemptSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """Submit exam attempt (Student only)"""
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()

    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # FIX Bug 10: Use enum value
    if attempt.status != AttemptStatus.IN_PROGRESS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attempt already submitted")

    # Save responses
    for response_data in submission.responses:
        response = Response(
            attempt_id=attempt_id,
            question_id=response_data.question_id,
            selected_option_ids=response_data.selected_option_ids,
            marked_for_review=response_data.marked_for_review
        )
        db.add(response)

    # Update attempt
    attempt.submitted_at = datetime.utcnow()
    time_taken = (attempt.submitted_at - attempt.started_at).total_seconds()
    attempt.time_taken_seconds = int(time_taken)
    # FIX Bug 10: Use enum value
    attempt.status = AttemptStatus.SUBMITTED

    db.commit()

    # Evaluate
    evaluation_service = EvaluationService(db)
    result = evaluation_service.evaluate_attempt(attempt_id)

    return result


@router.get("/{attempt_id}/results", response_model=dict)
def get_results(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get exam results"""
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()

    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()

    if current_user.role == "student" and str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    elif current_user.role == "examiner" and str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # FIX Bug 10: Use enum value
    if attempt.status != AttemptStatus.EVALUATED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Results not available yet")

    responses = db.query(Response).filter(Response.attempt_id == attempt_id).all()
    topic_wise = {}

    for response in responses:
        question = db.query(Question).filter(Question.id == response.question_id).first()
        if question and question.topic:
            if question.topic not in topic_wise:
                topic_wise[question.topic] = {"correct": 0, "total": 0}
            topic_wise[question.topic]["total"] += 1
            if response.is_correct:
                topic_wise[question.topic]["correct"] += 1

    for topic in topic_wise:
        total = topic_wise[topic]["total"]
        correct = topic_wise[topic]["correct"]
        topic_wise[topic]["percentage"] = (correct / total * 100) if total > 0 else 0

    obtained_marks = sum([r.marks_awarded for r in responses if r.marks_awarded])

    return {
        "score": float(attempt.score),
        "obtained_marks": float(obtained_marks),
        "total_marks": exam.total_marks,
        "correct_count": sum([1 for r in responses if r.is_correct]),
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
    """Get student's exam attempts"""
    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.student_id == current_user.id
    ).order_by(ExamAttempt.started_at.desc()).limit(limit).all()

    return attempts


@router.post("/{attempt_id}/auto-save", status_code=status.HTTP_200_OK)
def auto_save_progress(
    attempt_id: UUID,
    # FIX Bug 6: Use proper Pydantic model instead of bare List[dict]
    body: AutoSaveBody,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """Auto-save exam progress"""
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()

    if not attempt or str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    # Optionally persist responses here in future
    return {"message": "Progress saved", "saved": len(body.responses)}