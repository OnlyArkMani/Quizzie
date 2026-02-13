from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.models.exam import Exam
from app.models.question import Question, Option
from app.models.user import User

class ExamService:
    def __init__(self, db: Session):
        self.db = db
    
    def create_exam(self, title: str, description: str, duration_minutes: int, 
                    total_marks: int, pass_percentage: float, status: str, 
                    created_by: UUID) -> Exam:
        """
        Create a new exam
        """
        exam = Exam(
            title=title,
            description=description,
            duration_minutes=duration_minutes,
            total_marks=total_marks,
            pass_percentage=pass_percentage,
            status=status,
            created_by=created_by
        )
        
        self.db.add(exam)
        self.db.commit()
        self.db.refresh(exam)
        
        return exam
    
    def get_exam_by_id(self, exam_id: UUID) -> Optional[Exam]:
        """
        Get exam by ID
        """
        return self.db.query(Exam).filter(Exam.id == exam_id).first()
    
    def get_exams_by_examiner(self, examiner_id: UUID) -> List[Exam]:
        """
        Get all exams created by an examiner
        """
        return self.db.query(Exam).filter(Exam.created_by == examiner_id).all()
    
    def get_live_exams(self) -> List[Exam]:
        """
        Get all live exams
        """
        return self.db.query(Exam).filter(Exam.status == "live").all()
    
    def update_exam(self, exam_id: UUID, **kwargs) -> Optional[Exam]:
        """
        Update exam details
        """
        exam = self.get_exam_by_id(exam_id)
        
        if not exam:
            return None
        
        for key, value in kwargs.items():
            if hasattr(exam, key) and value is not None:
                setattr(exam, key, value)
        
        self.db.commit()
        self.db.refresh(exam)
        
        return exam
    
    def delete_exam(self, exam_id: UUID) -> bool:
        """
        Delete exam
        """
        exam = self.get_exam_by_id(exam_id)
        
        if not exam:
            return False
        
        self.db.delete(exam)
        self.db.commit()
        
        return True
    
    def add_question_to_exam(self, exam_id: UUID, question_text: str, 
                            question_type: str, marks: int, topic: Optional[str],
                            display_order: int, options: List[dict]) -> Question:
        """
        Add a question with options to an exam
        """
        question = Question(
            exam_id=exam_id,
            question_text=question_text,
            question_type=question_type,
            marks=marks,
            topic=topic,
            display_order=display_order
        )
        
        self.db.add(question)
        self.db.flush()
        
        # Add options
        for opt_data in options:
            option = Option(
                question_id=question.id,
                option_text=opt_data['option_text'],
                is_correct=opt_data['is_correct'],
                display_order=opt_data['display_order']
            )
            self.db.add(option)
        
        self.db.commit()
        self.db.refresh(question)
        
        return question
    
    def get_exam_questions(self, exam_id: UUID) -> List[Question]:
        """
        Get all questions for an exam
        """
        return self.db.query(Question).filter(
            Question.exam_id == exam_id
        ).order_by(Question.display_order).all()
    
    def get_exam_question_count(self, exam_id: UUID) -> int:
        """
        Get total number of questions in exam
        """
        return self.db.query(Question).filter(Question.exam_id == exam_id).count()