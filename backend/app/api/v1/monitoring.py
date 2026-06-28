"""
Proctoring API — v2 (async Celery-backed, with sync fallback)

Frame and audio uploads return 202 immediately when Celery/Redis is available.
When Redis is down (local dev), we skip straight to synchronous analysis using
module-level detector singletons — so MediaPipe only loads once per process,
not once per request.
"""
import base64
import logging
import threading
import time
from collections import deque
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from app.core.database import get_db
from app.core.cache import cache
from app.models.user import User
from app.models.attempt import ExamAttempt
from app.models.cheat_log import CheatLog
from app.api.deps import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Per-attempt upload rate limiter ────────────────────────────────────────────
# Frame/audio analysis is comparatively expensive (MediaPipe / a Celery task per
# request). Without a cap a client could flood these endpoints. We allow a small
# burst above the normal ~1 frame / detection_interval cadence and reject the
# rest with HTTP 429. In-process sliding window, keyed by attempt id.
_RATE_MAX_EVENTS = 8          # max uploads ...
_RATE_WINDOW_SEC = 5.0        # ... per this many seconds, per attempt
_rate_state: dict = {}
_rate_lock = threading.Lock()


def _check_rate_limit(attempt_id: str) -> bool:
    """Return True if the request is within the allowed rate, else False."""
    now = time.time()
    with _rate_lock:
        dq = _rate_state.get(attempt_id)
        if dq is None:
            dq = deque()
            _rate_state[attempt_id] = dq
        while dq and now - dq[0] > _RATE_WINDOW_SEC:
            dq.popleft()
        if len(dq) >= _RATE_MAX_EVENTS:
            return False
        dq.append(now)
        if len(_rate_state) > 5000:        # crude unbounded-growth guard
            for k in [k for k, v in _rate_state.items() if not v or now - v[-1] > 60]:
                _rate_state.pop(k, None)
        return True

# ── Sync-fallback singletons ───────────────────────────────────────────────────
# Loaded lazily on first use, then reused for the lifetime of the process.
# This mirrors what the Celery worker does — load once, analyze many.
_face_detector = None
_audio_analyzer = None


def _get_face_detector_sync():
    global _face_detector
    if _face_detector is None:
        from app.ai_monitor.face_detector import FaceDetector
        _face_detector = FaceDetector()
        logger.info("FaceDetector singleton initialised (sync fallback path)")
    return _face_detector


def _get_audio_analyzer_sync():
    global _audio_analyzer
    if _audio_analyzer is None:
        from app.ai_monitor.audio_analyzer import AudioAnalyzer
        _audio_analyzer = AudioAnalyzer()
        logger.info("AudioAnalyzer singleton initialised (sync fallback path)")
    return _audio_analyzer


def _celery_available() -> bool:
    """
    Fast check — if the Redis cache client is up, Celery broker is too.
    Avoids the slow Kombu connection-retry loop on a refused port.
    """
    return cache.is_available


def _get_celery_tasks():
    """Lazy import — keeps MediaPipe out of the web process on import."""
    from app.worker.tasks.proctoring_tasks import analyze_frame_task, analyze_audio_task
    return analyze_frame_task, analyze_audio_task


def _persist_flags_sync(attempt_id: str, flags: list, db: Session, event_type: str = "frame_analysis"):
    """
    Persist flags AND apply the health penalty using the request DB session.

    Delegates to the shared ``app.ai_monitor.health.record_violations`` writer
    so the sync path stays identical to the Celery worker path. Returns the
    record summary (health status + auto_submitted) or None if no attempt.
    """
    from app.ai_monitor import health, smoothing
    from app.models.proctoring_settings import ProctoringSettings

    # Temporal smoothing: drop transient single-frame flags before they cost HP.
    flags = smoothing.confirmed_flags(attempt_id, flags)
    if not flags:
        return None

    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        return None

    ps = db.query(ProctoringSettings).filter(
        ProctoringSettings.exam_id == attempt.exam_id
    ).first()

    return health.record_violations(db, attempt, flags, ps=ps, event_type=event_type)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/frame")
async def analyze_frame(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    attempt_id_str = str(attempt_id)
    if not _check_rate_limit(attempt_id_str):
        raise HTTPException(status_code=429, detail="Too many frames; slow down")

    image_bytes = await file.read()

    # ── Fast path: Celery available ────────────────────────────────────────────
    if _celery_available():
        try:
            image_b64 = base64.b64encode(image_bytes).decode()
            analyze_frame_task, _ = _get_celery_tasks()
            task = analyze_frame_task.apply_async(
                args=[attempt_id_str, image_b64],
                queue="proctoring",
            )
            return {"queued": True, "task_id": task.id}
        except Exception as e:
            logger.warning("apply_async failed despite Redis ping (%s) — falling through to sync", e)

    # ── Slow path: sync fallback (local dev without Redis) ─────────────────────
    try:
        from app.ai_monitor import snapshot

        result = _get_face_detector_sync().analyze_frame(image_bytes)
        record = None
        if result.get("flags"):
            snapshot.attach_snapshots(image_bytes, result["flags"])
            record = _persist_flags_sync(attempt_id_str, result["flags"], db)
        response = {"queued": False, "sync": True, "result": result}
        if record:
            response["health"] = record["health"]
            response["auto_submitted"] = record["auto_submitted"]
        return response
    except Exception as e:
        logger.exception("Sync frame analysis failed for attempt %s", attempt_id_str)
        raise HTTPException(status_code=500, detail=f"Frame analysis failed: {e}")


@router.post("/audio")
async def analyze_audio(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized")

    attempt_id_str = str(attempt_id)
    if not _check_rate_limit("audio:" + attempt_id_str):
        raise HTTPException(status_code=429, detail="Too many audio chunks; slow down")

    audio_bytes = await file.read()

    if _celery_available():
        try:
            audio_b64 = base64.b64encode(audio_bytes).decode()
            _, analyze_audio_task = _get_celery_tasks()
            task = analyze_audio_task.apply_async(
                args=[attempt_id_str, audio_b64],
                queue="proctoring",
            )
            return {"queued": True, "task_id": task.id}
        except Exception as e:
            logger.warning("apply_async failed despite Redis ping (%s) — falling through to sync", e)

    try:
        result = _get_audio_analyzer_sync().analyze_audio(audio_bytes)
        record = None
        if result.get("flags"):
            flags_as_dicts = [
                {"type": f, "severity": result.get("severity", "medium"), "message": f}
                for f in result["flags"]
            ]
            record = _persist_flags_sync(attempt_id_str, flags_as_dicts, db, event_type="audio_detection")
        response = {"queued": False, "sync": True, "result": result}
        if record:
            response["health"] = record["health"]
            response["auto_submitted"] = record["auto_submitted"]
        return response
    except Exception as e:
        logger.exception("Sync audio analysis failed for attempt %s", attempt_id_str)
        raise HTTPException(status_code=500, detail=f"Audio analysis failed: {e}")


@router.get("/flags/{attempt_id}", response_model=list)
def get_cheat_flags(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
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
