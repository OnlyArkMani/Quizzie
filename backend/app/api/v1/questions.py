from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from uuid import UUID
from app.core.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question, Option
from app.schemas.question import QuestionCreate, Question as QuestionSchema
from app.api.deps import get_current_user, require_role

router = APIRouter()

@router.post("/{exam_id}/questions", response_model=QuestionSchema, status_code=status.HTTP_201_CREATED)
def add_question(
    exam_id: UUID,
    question_data: QuestionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Add question to exam (Examiner only)
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
            detail="Not authorized to modify this exam"
        )
    
    # Validate question type
    if question_data.question_type not in ["single", "multiple"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid question type"
        )
    
    # Validate options
    if len(question_data.options) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least 2 options required"
        )
    
    correct_options = [opt for opt in question_data.options if opt.is_correct]
    if len(correct_options) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one correct option required"
        )
    
    # Create question
    new_question = Question(
        exam_id=exam_id,
        question_text=question_data.question_text,
        question_type=question_data.question_type,
        marks=question_data.marks,
        topic=question_data.topic,
        display_order=question_data.display_order
    )
    
    db.add(new_question)
    db.flush()
    
    # Create options
    for opt_data in question_data.options:
        new_option = Option(
            question_id=new_question.id,
            option_text=opt_data.option_text,
            is_correct=opt_data.is_correct,
            display_order=opt_data.display_order
        )
        db.add(new_option)
    
    db.commit()
    db.refresh(new_question)
    
    return new_question

@router.get("/{exam_id}/questions", response_model=List[QuestionSchema])
def list_questions(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List all questions for an exam
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found"
        )
    
    # Check permissions
    if current_user.role == "student" and exam.status != "live":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Exam is not available"
        )
    
    questions = db.query(Question).filter(
        Question.exam_id == exam_id
    ).order_by(Question.display_order).all()
    
    return questions

@router.delete("/{exam_id}/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    exam_id: UUID,
    question_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Delete question from exam (Examiner only)
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
            detail="Not authorized to modify this exam"
        )
    
    question = db.query(Question).filter(
        Question.id == question_id,
        Question.exam_id == exam_id
    ).first()
    
    if not question:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Question not found"
        )
    
    db.delete(question)
    db.commit()
    
    return None