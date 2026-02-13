from sqlalchemy.orm import Session
from uuid import UUID
from app.models.attempt import ExamAttempt, Response
from app.models.question import Question, Option
from app.models.exam import Exam
from typing import Dict

class EvaluationService:
    def __init__(self, db: Session):
        self.db = db
    
    def evaluate_attempt(self, attempt_id: UUID) -> Dict:
        """
        Evaluate exam attempt and calculate score
        """
        attempt = self.db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
        if not attempt:
            raise ValueError("Attempt not found")
        
        exam = self.db.query(Exam).filter(Exam.id == attempt.exam_id).first()
        responses = self.db.query(Response).filter(Response.attempt_id == attempt_id).all()
        
        total_marks = 0
        obtained_marks = 0
        correct_count = 0
        topic_stats = {}
        
        for response in responses:
            question = self.db.query(Question).filter(Question.id == response.question_id).first()
            
            # Get correct options
            correct_options = self.db.query(Option).filter(
                Option.question_id == question.id,
                Option.is_correct == True
            ).all()
            
            correct_option_ids = {opt.id for opt in correct_options}
            selected_option_ids = set(response.selected_option_ids)
            
            total_marks += question.marks
            
            # Check if answer is correct
            if correct_option_ids == selected_option_ids:
                obtained_marks += question.marks
                correct_count += 1
                response.is_correct = True
                response.marks_awarded = question.marks
            else:
                response.is_correct = False
                response.marks_awarded = 0
            
            # Topic-wise stats
            if question.topic:
                if question.topic not in topic_stats:
                    topic_stats[question.topic] = {'correct': 0, 'total': 0}
                topic_stats[question.topic]['total'] += 1
                if response.is_correct:
                    topic_stats[question.topic]['correct'] += 1
        
        # Update attempt
        attempt.score = (obtained_marks / total_marks * 100) if total_marks > 0 else 0
        attempt.status = 'evaluated'
        
        self.db.commit()
        
        return {
            'score': float(attempt.score),
            'obtained_marks': float(obtained_marks),
            'total_marks': total_marks,
            'correct_count': correct_count,
            'topic_wise': topic_stats
        }