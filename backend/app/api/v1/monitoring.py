"""
Proctoring API — v2 (async Celery-backed, with sync fallback)

Frame and audio uploads return immediately (202 Accepted) when Celery/Redis
is available. If Redis is down (e.g. local dev without Docker), the analysis
runs synchronously in-process and returns 200 so the API never hard-crashes.
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


def _run_frame_sync(attempt_id: str, image_b64: str) -> dict:
    """Synchronous fallback: run face detection in-process (no Celery needed)."""
    from app.ai_monitor.face_detector import FaceDetector
    from app.worker.tasks.proctoring_tasks import _persist_flags

    result = FaceDetector().analyze_frame(base64.b64decode(image_b64))
    if result.get("flags"):
        _persist_flags(attempt_id, result["flags"])
    return result


def _run_audio_sync(attempt_id: str, audio_b64: str) -> dict:
    """Synchronous fallback: run audio analysis in-process (no Celery needed)."""
    from app.ai_monitor.audio_analyzer import AudioAnalyzer
    from app.worker.tasks.proctoring_tasks import _persist_flags

    result = AudioAnalyzer().analyze_audio(base64.b64decode(audio_b64))
    if result.get("flags"):
        flags_as_dicts = [
            {"type": f, "severity": result.get("severity", "medium"), "message": f}
            for f in result["flags"]
        ]
        _persist_flags(attempt_id, flags_as_dicts)
    return result


@router.post("/frame")
async def analyze_frame(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Accept a webcam frame and enqueue AI analysis.
    Returns 202 when queued via Celery, 200 when run synchronously (no Redis).
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    image_bytes = await file.read()
    image_b64 = base64.b64encode(image_bytes).decode()
    attempt_id_str = str(attempt_id)

    # Try async Celery path first
    try:
        analyze_frame_task, _ = _get_celery()
        task = analyze_frame_task.apply_async(
            args=[attempt_id_str, image_b64],
            queue="proctoring",
        )
        return {"queued": True, "task_id": task.id, "status_code": 202}
    except Exception as celery_err:
        # Redis unavailable (local dev) — fall back to synchronous analysis
        logger.warning(
            "Celery unavailable (%s), running frame analysis synchronously for attempt %s",
            type(celery_err).__name__,
            attempt_id_str,
        )

    try:
        result = _run_frame_sync(attempt_id_str, image_b64)
        return {"queued": False, "sync": True, "result": result}
    except Exception as sync_err:
        logger.exception("Sync frame analysis failed for attempt %s", attempt_id_str)
        raise HTTPException(status_code=500, detail=f"Frame analysis failed: {sync_err}")


@router.post("/audio")
async def analyze_audio(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Accept an audio chunk and enqueue AI analysis.
    Returns 202 when queued via Celery, 200 when run synchronously (no Redis).
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    audio_bytes = await file.read()
    audio_b64 = base64.b64encode(audio_bytes).decode()
    attempt_id_str = str(attempt_id)

    try:
        _, analyze_audio_task = _get_celery()
        task = analyze_audio_task.apply_async(
            args=[attempt_id_str, audio_b64],
            queue="proctoring",
        )
        return {"queued": True, "task_id": task.id, "status_code": 202}
    except Exception as celery_err:
        logger.warning(
            "Celery unavailable (%s), running audio analysis synchronously for attempt %s",
            type(celery_err).__name__,
            attempt_id_str,
        )

    try:
        result = _run_audio_sync(attempt_id_str, audio_b64)
        return {"queued": False, "sync": True, "result": result}
    except Exception as sync_err:
        logger.exception("Sync audio analysis failed for attempt %s", attempt_id_str)
        raise HTTPException(status_code=500, detail=f"Audio analysis failed: {sync_err}")


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
