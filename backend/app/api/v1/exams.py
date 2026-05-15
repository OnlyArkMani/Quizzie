from fastapi import APIRouter, Depends, HTTPException, status as http_status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db
from app.core.cache import cache, key_exam_questions, key_exam_meta
from app.core.config import settings
from app.models.user import User
from app.models.exam import Exam, ExamStatus
from app.models.question import Question
from app.schemas.exam import ExamCreate, ExamUpdate, Exam as ExamSchema
from app.api.deps import get_current_user, require_role

router = APIRouter()


@router.post("/", response_model=ExamSchema, status_code=http_status.HTTP_201_CREATED)
def create_exam(
    exam_data: ExamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    new_exam = Exam(
        title=exam_data.title,
        description=exam_data.description,
        duration_minutes=exam_data.duration_minutes,
        total_marks=exam_data.total_marks,
        pass_percentage=exam_data.pass_percentage,
        status=ExamStatus.DRAFT,
        created_by=current_user.id
    )
    db.add(new_exam)
    db.commit()
    db.refresh(new_exam)
    return new_exam


@router.get("/", response_model=List[ExamSchema])
def list_exams(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    query = db.query(Exam)
    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

    if role == "examiner":
        query = query.filter(Exam.created_by == current_user.id)
    elif role == "student":
        query = query.filter(Exam.status == ExamStatus.LIVE)
        return query.order_by(Exam.created_at.desc()).all()

    if status_filter:
        query = query.filter(Exam.status == status_filter)

    return query.order_by(Exam.created_at.desc()).all()


@router.get("/{exam_id}", response_model=ExamSchema)
def get_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exam not found")

    if current_user.role == "examiner" and str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")

    if current_user.role == "student" and exam.status != ExamStatus.LIVE:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Exam not available")

    return exam


@router.put("/{exam_id}", response_model=ExamSchema)
async def update_exam(
    exam_id: UUID,
    exam_data: ExamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")

    for field, value in exam_data.dict(exclude_unset=True).items():
        setattr(exam, field, value)

    db.commit()
    db.refresh(exam)
    # Invalidate caches
    await cache.delete(key_exam_meta(str(exam_id)))
    await cache.delete(key_exam_questions(str(exam_id)))
    return exam


@router.delete("/{exam_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")

    db.delete(exam)
    db.commit()
    await cache.delete(key_exam_meta(str(exam_id)))
    await cache.delete(key_exam_questions(str(exam_id)))
    return None


@router.patch("/{exam_id}/status", response_model=ExamSchema)
async def update_exam_status(
    exam_id: UUID,
    new_status: str = Query(..., alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")
    if new_status not in ["draft", "live", "ended"]:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Invalid status")

    if new_status == "live":
        questions = db.query(Question).filter(Question.exam_id == exam_id).all()
        if questions:
            exam.total_marks = sum(q.marks for q in questions)

    exam.status = ExamStatus(new_status)
    db.commit()
    db.refresh(exam)
    await cache.delete(key_exam_meta(str(exam_id)))
    return exam


@router.get("/{exam_id}/questions", response_model=List[dict])
async def get_exam_questions(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get questions for an exam.
    Response is cached in Redis for CACHE_TTL_EXAM_QUESTIONS seconds
    (default 5 min) — so 500 students joining simultaneously only produce
    one DB query, not 500.
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exam not found")
    if current_user.role == "student" and exam.status != ExamStatus.LIVE:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Exam not available")

    cache_key = key_exam_questions(str(exam_id))
    cached = await cache.get(cache_key)
    if cached is not None:
        return cached

    # FIX: use joinedload to eliminate N+1 — one query for questions + options
    questions = (
        db.query(Question)
        .options(joinedload(Question.options))
        .filter(Question.exam_id == exam_id)
        .order_by(Question.display_order)
        .all()
    )

    result = []
    for q in questions:
        result.append({
            "id": str(q.id),
            "exam_id": str(q.exam_id),
            "question_text": q.question_text,
            "question_type": str(q.question_type).replace("QuestionType.", ""),
            "marks": q.marks,
            "topic": q.topic,
            "display_order": q.display_order,
            "options": [
                {
                    "id": str(opt.id),
                    "option_text": opt.option_text,
                    "is_correct": opt.is_correct,
                    "display_order": opt.display_order,
                }
                for opt in sorted(q.options, key=lambda x: x.display_order)
            ],
        })

    await cache.set(cache_key, result, ttl=settings.CACHE_TTL_EXAM_QUESTIONS)
    return result
