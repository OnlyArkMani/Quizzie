"""
Proctoring API — v2 (async Celery-backed, with sync fallback)

Frame and audio uploads return 202 immediately when Celery/Redis is available.
When Redis is down (local dev), we skip straight to synchronous analysis using
module-level detector singletons — so MediaPipe only loads once per process,
not once per request.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from typing import Optional
from uuid import UUID

from app.core.database import get_db, release_connection
from app.core import frame_mailbox, rate_limit
from app.core.cache import cache
from app.core.config import settings
from app.models.user import User
from app.models.attempt import AttemptStatus, ExamAttempt
from app.models.cheat_log import CheatLog
from app.api.deps import get_current_user, require_role

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_UPLOAD_BYTES = 2 * 1024 * 1024   # a JPEG webcam frame is ~30-100 KB

# ── Per-attempt upload rate limiter ────────────────────────────────────────────
# Frame/audio analysis is comparatively expensive (MediaPipe / a Celery task per
# request). We allow a small burst above the normal ~1 frame per
# detection_interval cadence and reject the rest with HTTP 429.
#
# The window lives in Redis (app.core.rate_limit) so the limit holds across
# every API replica and Uvicorn worker. The old in-process dict gave each
# process its own budget: N replicas behind a round-robin balancer = N× limit.


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
#
# These are ``async def`` because they await the upload body and Redis. Every
# blocking step (sync ORM, Celery's broker socket, MediaPipe) is pushed through
# run_in_threadpool so one slow frame can't stall the event loop for everyone.

def _check_attempt(db: Session, attempt_id: UUID, student_id) -> ExamAttempt:
    """Ownership + liveness. Frames for a closed/expired attempt are rejected."""
    from app.services.attempt_service import AttemptService

    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if str(attempt.student_id) != str(student_id):
        raise HTTPException(status_code=403, detail="Not authorized")
    svc = AttemptService(db)
    if attempt.status != AttemptStatus.IN_PROGRESS or svc.is_expired(attempt):
        svc.finalize_if_expired(attempt)
        raise HTTPException(status_code=409, detail="Attempt is not in progress")
    release_connection(db)   # the route awaits Redis / the upload body next
    return attempt


def _enqueue(kind: str, attempt_id: str, payload: bytes):
    """
    Blocking: hand the upload to the workers via the latest-frame mailbox.
    Returns {"queued": True, ...} or None if the caller should analyse inline.
    """
    outcome = frame_mailbox.post(kind, attempt_id, payload)
    if outcome == frame_mailbox.COALESCED:
        # A task for this attempt is already queued; it will read this (newer)
        # payload. Nothing to enqueue — this is the load-shedding path.
        return {"queued": True, "coalesced": True}
    if outcome == frame_mailbox.UNAVAILABLE:
        return None
    try:
        from app.worker.tasks.proctoring_tasks import analyze_latest_task
        task = analyze_latest_task.apply_async(args=[attempt_id, kind], queue="proctoring")
        return {"queued": True, "coalesced": False, "task_id": task.id}
    except Exception as e:
        logger.warning("apply_async failed (%s) — analysing inline", e)
        frame_mailbox.cancel_pending(kind, attempt_id)
        return None


def _analyze_frame_sync(attempt_id_str: str, image_bytes: bytes, db: Session) -> dict:
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


def _analyze_audio_sync(attempt_id_str: str, audio_bytes: bytes, db: Session) -> dict:
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


async def _handle_upload(kind: str, attempt_id: UUID, file: UploadFile, db: Session, user: User):
    await run_in_threadpool(_check_attempt, db, attempt_id, user.id)

    attempt_id_str = str(attempt_id)
    if not await rate_limit.allow(
        f"{kind}:{attempt_id_str}",
        settings.PROCTOR_RATE_MAX_EVENTS,
        settings.PROCTOR_RATE_WINDOW_SEC,
    ):
        raise HTTPException(status_code=429, detail=f"Too many {kind} uploads; slow down")

    payload = await file.read()
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Upload too large")

    # ── Fast path: Celery available ────────────────────────────────────────
    if _celery_available():
        queued = await run_in_threadpool(_enqueue, kind, attempt_id_str, payload)
        if queued is not None:
            return queued

    # ── Slow path: sync fallback (local dev without Redis) ─────────────────
    try:
        fn = _analyze_frame_sync if kind == "frame" else _analyze_audio_sync
        return await run_in_threadpool(fn, attempt_id_str, payload, db)
    except Exception as e:
        logger.exception("Sync %s analysis failed for attempt %s", kind, attempt_id_str)
        raise HTTPException(status_code=500, detail=f"{kind.title()} analysis failed: {e}")


@router.post("/frame")
async def analyze_frame(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    return await _handle_upload("frame", attempt_id, file, db, current_user)


@router.post("/audio")
async def analyze_audio(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    return await _handle_upload("audio", attempt_id, file, db, current_user)


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
