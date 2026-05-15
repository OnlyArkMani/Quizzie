"""
Proctoring API — v2 (async Celery-backed)

Frame and audio uploads return immediately (202 Accepted).
The actual AI analysis runs in a Celery worker process, keeping the
FastAPI event loop free for hundreds of concurrent students.
"""
import base64
import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from uuid import UUID

from app.core.database import get_db
from app.models.user import User
from app.models.attempt import ExamAttempt
from app.models.cheat_log import CheatLog
from app.api.deps import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()


def _get_celery():
    """Lazy import so the web process never loads MediaPipe."""
    from app.worker.tasks.proctoring_tasks import analyze_frame_task, analyze_audio_task
    return analyze_frame_task, analyze_audio_task


@router.post("/frame", status_code=status.HTTP_202_ACCEPTED)
async def analyze_frame(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Accept a webcam frame and enqueue AI analysis.
    Returns 202 immediately — result is persisted by the Celery worker.
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    image_bytes = await file.read()
    image_b64 = base64.b64encode(image_bytes).decode()

    analyze_frame_task, _ = _get_celery()
    task = analyze_frame_task.apply_async(
        args=[str(attempt_id), image_b64],
        queue="proctoring",
    )

    return {"queued": True, "task_id": task.id}


@router.post("/audio", status_code=status.HTTP_202_ACCEPTED)
async def analyze_audio(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Accept an audio chunk and enqueue AI analysis.
    Returns 202 immediately.
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    audio_bytes = await file.read()
    audio_b64 = base64.b64encode(audio_bytes).decode()

    _, analyze_audio_task = _get_celery()
    task = analyze_audio_task.apply_async(
        args=[str(attempt_id), audio_b64],
        queue="proctoring",
    )

    return {"queued": True, "task_id": task.id}


@router.get("/flags/{attempt_id}", response_model=list)
def get_cheat_flags(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all cheat flags for an attempt."""
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    if current_user.role == "student" and str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    logs = db.query(CheatLog).filter(CheatLog.attempt_id == attempt_id).all()
    return [
        {
            "id": str(log.id),
            "flag_type": log.flag_type,
            "severity": log.severity,
            "timestamp": log.timestamp.isoformat(),
            "metadata": log.meta_data,
        }
        for log in logs
    ]
