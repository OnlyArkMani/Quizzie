from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Dict, List
from uuid import UUID
from app.models.exam import Exam
from app.models.attempt import ExamAttempt, Response
from app.models.question import Question
from app.models.user import User

class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db
    
    def get_exam_statistics(self, exam_id: UUID) -> Dict:
        """
        Get comprehensive statistics for an exam
        """
        attempts = self.db.query(ExamAttempt).filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.status == "evaluated"
        ).all()
        
        if not attempts:
            return {
                'total_attempts': 0,
                'average_score': 0,
                'highest_score': 0,
                'lowest_score': 0,
                'pass_rate': 0,
                'average_time': 0
            }
        
        scores = [float(attempt.score) for attempt in attempts]
        times = [attempt.time_taken_seconds for attempt in attempts if attempt.time_taken_seconds]
        
        exam = self.db.query(Exam).filter(Exam.id == exam_id).first()
        passed = sum(1 for score in scores if score >= float(exam.pass_percentage))
        
        return {
            'total_attempts': len(attempts),
            'average_score': sum(scores) / len(scores),
            'highest_score': max(scores),
            'lowest_score': min(scores),
            'pass_rate': (passed / len(attempts)) * 100 if attempts else 0,
            'average_time': sum(times) / len(times) if times else 0
        }
    
    def get_topic_wise_performance(self, exam_id: UUID) -> Dict[str, Dict]:
        """
        Get topic-wise performance statistics
        """
        attempts = self.db.query(ExamAttempt).filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.status == "evaluated"
        ).all()
        
        topic_stats = {}
        
        for attempt in attempts:
            responses = self.db.query(Response).filter(
                Response.attempt_id == attempt.id
            ).all()
            
            for response in responses:
                question = self.db.query(Question).filter(
                    Question.id == response.question_id
                ).first()
                
                if question and question.topic:
                    if question.topic not in topic_stats:
                        topic_stats[question.topic] = {'correct': 0, 'total': 0}
                    
                    topic_stats[question.topic]['total'] += 1
                    if response.is_correct:
                        topic_stats[question.topic]['correct'] += 1
        
        # Calculate percentages
        for topic in topic_stats:
            total = topic_stats[topic]['total']
            correct = topic_stats[topic]['correct']
            topic_stats[topic]['percentage'] = (correct / total * 100) if total > 0 else 0
        
        return topic_stats
    
    def get_leaderboard(self, exam_id: UUID, limit: int = 10) -> List[Dict]:
        """
        Get top performers for an exam
        """
        attempts = self.db.query(ExamAttempt).filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.status == "evaluated"
        ).order_by(desc(ExamAttempt.score)).limit(limit).all()
        
        leaderboard = []
        
        for rank, attempt in enumerate(attempts, start=1):
            student = self.db.query(User).filter(User.id == attempt.student_id).first()
            
            leaderboard.append({
                'rank': rank,
                'student_id': str(attempt.student_id),
                'student_name': student.full_name if student else "Unknown",
                'score': float(attempt.score),
                'time_taken_seconds': attempt.time_taken_seconds
            })
        
        return leaderboard
    
    def get_student_performance(self, student_id: UUID) -> Dict:
        """
        Get overall performance for a student
        """
        attempts = self.db.query(ExamAttempt).filter(
            ExamAttempt.student_id == student_id,
            ExamAttempt.status == "evaluated"
        ).all()
        
        if not attempts:
            return {
                'total_exams': 0,
                'average_score': 0,
                'exams_taken': 0,
                'highest_score': 0,
                'lowest_score': 0
            }
        
        scores = [float(attempt.score) for attempt in attempts]
        
        return {
            'total_exams': self.db.query(Exam).filter(Exam.status == "live").count(),
            'average_score': sum(scores) / len(scores),
            'exams_taken': len(attempts),
            'highest_score': max(scores),
            'lowest_score': min(scores)
        }
    
    def get_score_distribution(self, exam_id: UUID) -> List[Dict]:
        """
        Get score distribution in ranges
        """
        attempts = self.db.query(ExamAttempt).filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.status == "evaluated"
        ).all()
        
        scores = [float(attempt.score) for attempt in attempts]
        
        distribution = [
            {'range': '0-40', 'count': sum(1 for s in scores if s < 40)},
            {'range': '40-60', 'count': sum(1 for s in scores if 40 <= s < 60)},
            {'range': '60-80', 'count': sum(1 for s in scores if 60 <= s < 80)},
            {'range': '80-100', 'count': sum(1 for s in scores if s >= 80)},
        ]
        
        return distribution
    
    def get_examiner_statistics(self, examiner_id: UUID) -> Dict:
        """
        Get overall statistics for an examiner
        """
        exams = self.db.query(Exam).filter(Exam.created_by == examiner_id).all()
        exam_ids = [exam.id for exam in exams]
        
        total_attempts = self.db.query(ExamAttempt).filter(
            ExamAttempt.exam_id.in_(exam_ids)
        ).count()
        
        live_exams = sum(1 for exam in exams if exam.status == "live")
        
        return {
            'total_exams': len(exams),
            'live_exams': live_exams,
            'draft_exams': sum(1 for exam in exams if exam.status == "draft"),
            'ended_exams': sum(1 for exam in exams if exam.status == "ended"),
            'total_attempts': total_attempts
        }