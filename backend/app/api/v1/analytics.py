"""
Analytics API — N+1 fixed with aggregate SQL queries.
All heavy reads now do one JOIN instead of nested Python loops.
Leaderboard results are cached in Redis.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import List
from uuid import UUID
import csv
import io

from app.core.database import get_db
from app.core.cache import cache, key_leaderboard
from app.core.config import settings
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
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # Single aggregate query instead of Python loop
    stats = db.query(
        func.count(ExamAttempt.id).label("total"),
        func.avg(ExamAttempt.score).label("avg_score"),
        func.max(ExamAttempt.score).label("max_score"),
        func.min(ExamAttempt.score).label("min_score"),
    ).filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.status == "evaluated"
    ).one()

    if not stats.total:
        return {"total_attempts": 0, "average_score": 0, "highest_score": 0,
                "lowest_score": 0, "pass_percentage": 0, "topic_wise_stats": {},
                "score_distribution": []}

    passed = db.query(func.count(ExamAttempt.id)).filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.status == "evaluated",
        ExamAttempt.score >= exam.pass_percentage,
    ).scalar()

    # Topic-wise stats — one join query
    topic_rows = db.query(
        Question.topic,
        func.count(Response.id).label("total"),
        func.sum(case((Response.is_correct == True, 1), else_=0)).label("correct"),
    ).join(Response, Response.question_id == Question.id)\
     .join(ExamAttempt, ExamAttempt.id == Response.attempt_id)\
     .filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.status == "evaluated",
        Question.topic.isnot(None),
    ).group_by(Question.topic).all()

    topic_wise = {
        row.topic: {
            "correct": int(row.correct or 0),
            "total": int(row.total),
            "percentage": round((int(row.correct or 0) / int(row.total)) * 100, 1) if row.total else 0,
        }
        for row in topic_rows
    }

    # Score distribution — one query with CASE
    dist_rows = db.query(
        func.sum(case((ExamAttempt.score < 40, 1), else_=0)).label("r0_40"),
        func.sum(case(((ExamAttempt.score >= 40) & (ExamAttempt.score < 60), 1), else_=0)).label("r40_60"),
        func.sum(case(((ExamAttempt.score >= 60) & (ExamAttempt.score < 80), 1), else_=0)).label("r60_80"),
        func.sum(case((ExamAttempt.score >= 80, 1), else_=0)).label("r80_100"),
    ).filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.status == "evaluated",
    ).one()

    score_distribution = [
        {"range": "0-40",   "count": int(dist_rows.r0_40 or 0)},
        {"range": "40-60",  "count": int(dist_rows.r40_60 or 0)},
        {"range": "60-80",  "count": int(dist_rows.r60_80 or 0)},
        {"range": "80-100", "count": int(dist_rows.r80_100 or 0)},
    ]

    return {
        "total_attempts": stats.total,
        "average_score": round(float(stats.avg_score or 0), 2),
        "highest_score": round(float(stats.max_score or 0), 2),
        "lowest_score": round(float(stats.min_score or 0), 2),
        "pass_percentage": round((passed / stats.total) * 100, 2) if stats.total else 0,
        "topic_wise_stats": topic_wise,
        "score_distribution": score_distribution,
    }


@router.get("/exam/{exam_id}/leaderboard", response_model=List[dict])
async def get_leaderboard(
    exam_id: UUID,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    ckey = key_leaderboard(str(exam_id))
    cached = await cache.get(ckey)
    if cached:
        return cached

    # Single join query — no per-student lookup
    rows = db.query(
        ExamAttempt.id,
        ExamAttempt.score,
        ExamAttempt.time_taken_seconds,
        User.full_name,
    ).join(User, User.id == ExamAttempt.student_id)\
     .filter(ExamAttempt.exam_id == exam_id, ExamAttempt.status == "evaluated")\
     .order_by(ExamAttempt.score.desc())\
     .limit(limit).all()

    leaderboard = [
        {
            "rank": i + 1,
            "student_name": row.full_name,
            "score": float(row.score),
            "time_taken_seconds": row.time_taken_seconds,
        }
        for i, row in enumerate(rows)
    ]

    await cache.set(ckey, leaderboard, ttl=settings.CACHE_TTL_LEADERBOARD)
    return leaderboard


@router.get("/student/me/stats", response_model=dict)
def get_student_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    stats = db.query(
        func.count(ExamAttempt.id).label("taken"),
        func.avg(ExamAttempt.score).label("avg"),
    ).filter(
        ExamAttempt.student_id == current_user.id,
        ExamAttempt.status == "evaluated",
    ).one()

    total_live = db.query(func.count(Exam.id)).filter(Exam.status == "live").scalar()

    return {
        "totalExams": total_live,
        "averageScore": round(float(stats.avg or 0), 2),
        "examsTaken": stats.taken,
    }


@router.get("/examiner/stats", response_model=dict)
def get_examiner_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    counts = db.query(
        func.count(Exam.id).label("total"),
        func.sum(case((Exam.status == "live", 1), else_=0)).label("live"),
    ).filter(Exam.created_by == current_user.id).one()

    exam_ids_sub = db.query(Exam.id).filter(Exam.created_by == current_user.id).subquery()
    total_attempts = db.query(func.count(ExamAttempt.id)).filter(
        ExamAttempt.exam_id.in_(exam_ids_sub)
    ).scalar()

    return {
        "totalExams": counts.total or 0,
        "liveExams": int(counts.live or 0),
        "totalAttempts": total_attempts or 0,
    }


@router.get("/exam/{exam_id}/export")
def export_results(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["examiner", "admin"]))
):
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.created_by != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")

    # One join query for all attempt data
    rows = db.query(
        User.full_name,
        User.email,
        ExamAttempt.score,
        ExamAttempt.time_taken_seconds,
        ExamAttempt.cheating_flags,
        func.sum(Response.marks_awarded).label("obtained"),
    ).join(User, User.id == ExamAttempt.student_id)\
     .outerjoin(Response, Response.attempt_id == ExamAttempt.id)\
     .filter(ExamAttempt.exam_id == exam_id, ExamAttempt.status == "evaluated")\
     .group_by(User.full_name, User.email, ExamAttempt.score,
               ExamAttempt.time_taken_seconds, ExamAttempt.cheating_flags)\
     .all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Student Name", "Email", "Score (%)", "Marks Obtained",
                     "Total Marks", "Time (s)", "Cheating Flags", "Status"])
    for r in rows:
        writer.writerow([
            r.full_name, r.email, f"{r.score:.2f}",
            f"{float(r.obtained or 0):.2f}", exam.total_marks,
            r.time_taken_seconds, r.cheating_flags,
            "Pass" if float(r.score) >= float(exam.pass_percentage) else "Fail",
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=exam_{exam_id}_results.csv"},
    )
