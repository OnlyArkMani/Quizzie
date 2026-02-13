from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from uuid import UUID
import csv
import io
from app.core.database import get_db
from app.models.user import User
from app.models.exam import Exam
from app.models.attempt import ExamAttempt, Response
from app.models.question import Question
from app.schemas.analytics import ExamSummary, LeaderboardEntry, StudentPerformance
from app.api.deps import get_current_user, require_role

router = APIRouter()

@router.get("/exam/{exam_id}/summary", response_model=dict)
def get_exam_summary(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Get exam analytics summary (Examiner only)
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
            detail="Not authorized"
        )
    
    # Get all evaluated attempts
    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.status == "evaluated"
    ).all()
    
    if not attempts:
        return {
            'total_attempts': 0,
            'average_score': 0,
            'highest_score': 0,
            'lowest_score': 0,
            'pass_percentage': 0,
            'topic_wise_stats': {},
            'score_distribution': []
        }
    
    # Calculate statistics
    scores = [float(attempt.score) for attempt in attempts]
    total_attempts = len(attempts)
    average_score = sum(scores) / total_attempts
    highest_score = max(scores)
    lowest_score = min(scores)
    
    # Pass percentage
    passed = sum([1 for score in scores if score >= float(exam.pass_percentage)])
    pass_percentage = (passed / total_attempts * 100) if total_attempts > 0 else 0
    
    # Topic-wise statistics
    topic_wise_stats = {}
    for attempt in attempts:
        responses = db.query(Response).filter(Response.attempt_id == attempt.id).all()
        
        for response in responses:
            question = db.query(Question).filter(Question.id == response.question_id).first()
            if question and question.topic:
                if question.topic not in topic_wise_stats:
                    topic_wise_stats[question.topic] = {'correct': 0, 'total': 0}
                
                topic_wise_stats[question.topic]['total'] += 1
                if response.is_correct:
                    topic_wise_stats[question.topic]['correct'] += 1
    
    # Calculate topic percentages
    for topic in topic_wise_stats:
        total = topic_wise_stats[topic]['total']
        correct = topic_wise_stats[topic]['correct']
        topic_wise_stats[topic]['percentage'] = (correct / total * 100) if total > 0 else 0
    
    # Score distribution (0-40, 40-60, 60-80, 80-100)
    score_distribution = [
        {'range': '0-40', 'count': sum([1 for s in scores if s < 40])},
        {'range': '40-60', 'count': sum([1 for s in scores if 40 <= s < 60])},
        {'range': '60-80', 'count': sum([1 for s in scores if 60 <= s < 80])},
        {'range': '80-100', 'count': sum([1 for s in scores if s >= 80])},
    ]
    
    return {
        'total_attempts': total_attempts,
        'average_score': round(average_score, 2),
        'highest_score': round(highest_score, 2),
        'lowest_score': round(lowest_score, 2),
        'pass_percentage': round(pass_percentage, 2),
        'topic_wise_stats': topic_wise_stats,
        'score_distribution': score_distribution
    }

@router.get("/exam/{exam_id}/leaderboard", response_model=List[dict])
def get_leaderboard(
    exam_id: UUID,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Get exam leaderboard (Examiner only)
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
            detail="Not authorized"
        )
    
    # Get top attempts
    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.status == "evaluated"
    ).order_by(ExamAttempt.score.desc()).limit(limit).all()
    
    leaderboard = []
    for rank, attempt in enumerate(attempts, start=1):
        student = db.query(User).filter(User.id == attempt.student_id).first()
        leaderboard.append({
            'rank': rank,
            'student_name': student.full_name if student else "Unknown",
            'score': float(attempt.score),
            'time_taken_seconds': attempt.time_taken_seconds
        })
    
    return leaderboard

@router.get("/student/me/stats", response_model=dict)
def get_student_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Get student's performance statistics
    """
    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.student_id == current_user.id,
        ExamAttempt.status == "evaluated"
    ).all()
    
    if not attempts:
        return {
            'totalExams': 0,
            'averageScore': 0,
            'examsTaken': 0
        }
    
    scores = [float(attempt.score) for attempt in attempts]
    
    return {
        'totalExams': db.query(Exam).filter(Exam.status == "live").count(),
        'averageScore': round(sum(scores) / len(scores), 2) if scores else 0,
        'examsTaken': len(attempts)
    }

@router.get("/examiner/stats", response_model=dict)
def get_examiner_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Get examiner's statistics
    """
    total_exams = db.query(Exam).filter(Exam.created_by == current_user.id).count()
    live_exams = db.query(Exam).filter(
        Exam.created_by == current_user.id,
        Exam.status == "live"
    ).count()
    
    # Get total attempts across all exams
    exam_ids = [e.id for e in db.query(Exam.id).filter(Exam.created_by == current_user.id).all()]
    total_attempts = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id.in_(exam_ids)
    ).count()
    
    return {
        'totalExams': total_exams,
        'liveExams': live_exams,
        'totalAttempts': total_attempts
    }

@router.get("/exam/{exam_id}/export")
def export_results(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    """
    Export exam results as CSV
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
            detail="Not authorized"
        )
    
    # Get all attempts
    attempts = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.status == "evaluated"
    ).all()
    
    # Create CSV
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow([
        'Student Name',
        'Email',
        'Score (%)',
        'Marks Obtained',
        'Total Marks',
        'Time Taken (seconds)',
        'Cheating Flags',
        'Status'
    ])
    
    # Data
    for attempt in attempts:
        student = db.query(User).filter(User.id == attempt.student_id).first()
        responses = db.query(Response).filter(Response.attempt_id == attempt.id).all()
        obtained_marks = sum([r.marks_awarded for r in responses if r.marks_awarded])
        
        writer.writerow([
            student.full_name if student else "Unknown",
            student.email if student else "Unknown",
            f"{attempt.score:.2f}",
            f"{obtained_marks:.2f}",
            exam.total_marks,
            attempt.time_taken_seconds,
            attempt.cheating_flags,
            "Pass" if float(attempt.score) >= float(exam.pass_percentage) else "Fail"
        ])
    
    output.seek(0)
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=exam_{exam_id}_results.csv"
        }
    )