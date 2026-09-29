from fastapi import APIRouter, Depends, HTTPException, status as http_status, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from uuid import UUID

from app.core.database import get_db, release_connection, run_db
from app.core.cache import cache, invalidate_sync, key_exam_questions, key_exam_meta
from app.core.config import settings
from app.models.user import User
from app.models.exam import Exam, ExamStatus
from app.models.question import Question
from app.schemas.exam import ExamCreate, ExamUpdate, Exam as ExamSchema
from app.api.deps import get_current_user, require_role

router = APIRouter()


def _exam_dto(exam: Exam) -> dict:
    """Plain data, so the DB transaction can end before serialisation (run_db)."""
    return ExamSchema.model_validate(exam).model_dump()


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
async def list_exams(
    status_filter: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    def work():
        query = db.query(Exam)
        role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)

        if role == "examiner":
            query = query.filter(Exam.created_by == current_user.id)
        elif role == "student":
            query = query.filter(Exam.status == ExamStatus.LIVE)
            return [_exam_dto(e) for e in query.order_by(Exam.created_at.desc()).all()]

        if status_filter:
            query = query.filter(Exam.status == status_filter)

        return [_exam_dto(e) for e in query.order_by(Exam.created_at.desc()).all()]

    return await run_db(db, work)


@router.get("/{exam_id}", response_model=ExamSchema)
async def get_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    def work():
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exam not found")

        if current_user.role == "examiner" and str(exam.created_by) != str(current_user.id):
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")

        if current_user.role == "student" and exam.status != ExamStatus.LIVE:
            raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Exam not available")

        return _exam_dto(exam)

    return await run_db(db, work)


@router.put("/{exam_id}", response_model=ExamSchema)
def update_exam(
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
    # Invalidate AFTER commit: invalidating first leaves a window where a
    # concurrent reader re-caches the old row and it lives for a full TTL.
    invalidate_sync(key_exam_meta(str(exam_id)), key_exam_questions(str(exam_id)))
    return exam


@router.delete("/{exam_id}", status_code=http_status.HTTP_204_NO_CONTENT)
def delete_exam(
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
    invalidate_sync(key_exam_meta(str(exam_id)), key_exam_questions(str(exam_id)))
    return None


@router.patch("/{exam_id}/status", response_model=ExamSchema)
def update_exam_status(
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
    invalidate_sync(key_exam_meta(str(exam_id)))
    return exam


def _load_exam_meta(db: Session, exam_id: UUID) -> Optional[dict]:
    try:
        exam = db.query(Exam).filter(Exam.id == exam_id).first()
        if not exam:
            return None
        return {"status": exam.status.value, "created_by": str(exam.created_by)}
    finally:
        release_connection(db)   # don't hold a pooled connection across the next await


def _load_questions(db: Session, exam_id: UUID) -> List[dict]:
    """Full question payload INCLUDING the answer key (server-side cache only)."""
    # joinedload: one query for questions + options (no N+1)
    questions = (
        db.query(Question)
        .options(joinedload(Question.options))
        .filter(Question.exam_id == exam_id)
        .order_by(Question.display_order)
        .all()
    )
    payload = [
        {
            "id": str(q.id),
            "exam_id": str(q.exam_id),
            "question_text": q.question_text,
            # .value, not str(): str() of a (str, Enum) member is "QuestionType.MULTIPLE",
            # which the frontend never matched (multi-select/coding questions broke).
            "question_type": q.question_type.value,
            "marks": q.marks,
            "topic": q.topic,
            "display_order": q.display_order,
            "reference_answer": q.reference_answer,
            "language": q.language,
            "options": [
                {
                    "id": str(opt.id),
                    "option_text": opt.option_text,
                    "is_correct": opt.is_correct,
                    "display_order": opt.display_order,
                }
                for opt in sorted(q.options, key=lambda x: x.display_order)
            ],
        }
        for q in questions
    ]
    release_connection(db)
    return payload


def _student_view(questions: List[dict]) -> List[dict]:
    """
    Strip everything that reveals answers. The previous version sent
    ``is_correct`` for every option to students — the whole answer key was one
    DevTools "Network" tab away.
    """
    return [
        {
            **{k: v for k, v in q.items() if k != "reference_answer"},
            "options": [
                {k: v for k, v in o.items() if k != "is_correct"} for o in q["options"]
            ],
        }
        for q in questions
    ]
    release_connection(db)
    return payload


@router.get("/{exam_id}/questions", response_model=List[dict])
async def get_exam_questions(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get questions for an exam.

    Hot path when an exam goes live (every student loads it at once), so it
    does zero DB work on a warm cache: both the exam's status/owner (60 s TTL)
    and the question list (5 min TTL) are cached. On a cold or expired cache,
    ``get_or_compute`` lets exactly one request query Postgres while the rest
    wait for its result (no stampede). DB access runs in the threadpool.
    """
    meta = await cache.get_or_compute(
        key_exam_meta(str(exam_id)), settings.CACHE_TTL_EXAM_META,
        lambda: run_in_threadpool(_load_exam_meta, db, exam_id),
    )
    if not meta:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Exam not found")

    role = current_user.role.value if hasattr(current_user.role, "value") else str(current_user.role)
    if role == "student" and meta["status"] != ExamStatus.LIVE.value:
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Exam not available")
    if role == "examiner" and meta["created_by"] != str(current_user.id):
        raise HTTPException(status_code=http_status.HTTP_403_FORBIDDEN, detail="Not authorized")

    questions = await cache.get_or_compute(
        key_exam_questions(str(exam_id)), settings.CACHE_TTL_EXAM_QUESTIONS,
        lambda: run_in_threadpool(_load_questions, db, exam_id),
    )
    return questions if role in ("examiner", "admin") else _student_view(questions)
