from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.core.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.schemas.exam import ExamCreate, ExamUpdate, Exam as ExamSchema
from app.api.deps import get_current_user, require_role

router = APIRouter()

@router.post("/", response_model=ExamSchema, status_code=status.HTTP_201_CREATED)
def create_exam(
    exam_data: ExamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Create a new exam (Examiner only)
    """
    new_exam = Exam(
        title=exam_data.title,
        description=exam_data.description,
        duration_minutes=exam_data.duration_minutes,
        total_marks=exam_data.total_marks,
        pass_percentage=exam_data.pass_percentage,
        status=exam_data.status,
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
    """
    List all exams (filtered by role)
    """
    query = db.query(Exam)
    
    if current_user.role == "examiner":
        # Examiners see only their exams
        query = query.filter(Exam.created_by == current_user.id)
    elif current_user.role == "student":
        # Students see only live exams
        query = query.filter(Exam.status == "live")
    
    if status_filter:
        query = query.filter(Exam.status == status_filter)
    
    exams = query.order_by(Exam.created_at.desc()).all()
    return exams

@router.get("/{exam_id}", response_model=ExamSchema)
def get_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get exam details
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found"
        )
    
    # Check permissions
    if current_user.role == "examiner" and exam.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to view this exam"
        )
    
    if current_user.role == "student" and exam.status != "live":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Exam is not available"
        )
    
    return exam

@router.put("/{exam_id}", response_model=ExamSchema)
def update_exam(
    exam_id: UUID,
    exam_data: ExamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Update exam (Examiner only)
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found"
        )
    
    if exam.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this exam"
        )
    
    # Update fields
    update_data = exam_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(exam, field, value)
    
    db.commit()
    db.refresh(exam)
    
    return exam

@router.delete("/{exam_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_exam(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Delete exam (Examiner only)
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found"
        )
    
    if exam.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to delete this exam"
        )
    
    db.delete(exam)
    db.commit()
    
    return None

@router.patch("/{exam_id}/status", response_model=ExamSchema)
def update_exam_status(
    exam_id: UUID,
    status: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Update exam status (draft/live/ended)
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found"
        )
    
    if exam.created_by != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to update this exam"
        )
    
    if status not in ["draft", "live", "ended"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid status"
        )
    
    exam.status = status
    db.commit()
    db.refresh(exam)
    
    return exam