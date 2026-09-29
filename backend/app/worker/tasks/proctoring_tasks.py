"""
Celery tasks for AI proctoring.

``analyze_latest_task`` is the current path (payload via the Redis mailbox,
see app.core.frame_mailbox). ``analyze_frame_task`` / ``analyze_audio_task``
(payload inside the message) are kept so tasks already queued during a deploy
still run.

These run in separate worker processes, completely off the FastAPI event loop.
The web API enqueues a task and returns immediately (fire-and-forget for frame
analysis). Results are persisted to PostgreSQL by the worker itself.
"""
import logging
from typing import Optional
from uuid import UUID

from app.worker.celery_app import celery_app
from app.core.database import SessionLocal
from app.models.attempt import ExamAttempt
from app.models.cheat_log import CheatLog, CheatSeverity
from app.ai_monitor.face_detector import FaceDetector
from app.ai_monitor.audio_analyzer import AudioAnalyzer

logger = logging.getLogger(__name__)

# ── Module-level singletons inside the worker process ──────────────────────────
# Each Celery worker process loads these ONCE on startup.
# The web API process never imports or instantiates these — huge RAM saving.
_face_detector: Optional[FaceDetector] = None
_audio_analyzer: Optional[AudioAnalyzer] = None


def _get_face_detector() -> FaceDetector:
    global _face_detector
    if _face_detector is None:
        _face_detector = FaceDetector()
    return _face_detector


def _get_audio_analyzer() -> AudioAnalyzer:
    global _audio_analyzer
    if _audio_analyzer is None:
        _audio_analyzer = AudioAnalyzer()
    return _audio_analyzer


# ── Tasks ──────────────────────────────────────────────────────────────────────

@celery_app.task(
    name="app.worker.tasks.proctoring_tasks.analyze_frame_task",
    bind=True,
    max_retries=2,
    default_retry_delay=2,
)
def analyze_frame_task(self, attempt_id: str, image_bytes_b64: str) -> dict:
    """
    Decode a base64 webcam frame, run MediaPipe FaceMesh analysis,
    persist any flags to cheat_logs, and return the result dict.
    """
    import base64

    try:
        from app.ai_monitor import snapshot

        image_bytes = base64.b64decode(image_bytes_b64)
        result = _get_face_detector().analyze_frame(image_bytes)

        if result.get("flags"):
            snapshot.attach_snapshots(image_bytes, result["flags"])
            _persist_flags(attempt_id, result["flags"])

        return result

    except Exception as exc:
        logger.exception("analyze_frame_task failed for attempt %s", attempt_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.worker.tasks.proctoring_tasks.analyze_audio_task",
    bind=True,
    max_retries=2,
    default_retry_delay=2,
)
def analyze_audio_task(self, attempt_id: str, audio_bytes_b64: str) -> dict:
    """
    Decode a base64 audio chunk, run RMS analysis,
    persist any flags to cheat_logs, and return the result dict.
    """
    import base64

    try:
        audio_bytes = base64.b64decode(audio_bytes_b64)
        result = _get_audio_analyzer().analyze_audio(audio_bytes)

        if result.get("flags"):
            flags_as_dicts = [
                {"type": f, "severity": result.get("severity", "medium"), "message": f}
                for f in result["flags"]
            ]
            _persist_flags(attempt_id, flags_as_dicts)

        return result

    except Exception as exc:
        logger.exception("analyze_audio_task failed for attempt %s", attempt_id)
        raise self.retry(exc=exc)


@celery_app.task(
    name="app.worker.tasks.proctoring_tasks.analyze_latest_task",
    bind=True,
    max_retries=0,          # a retry would analyse an even staler frame; the next
                            # upload re-enqueues anyway (see frame_mailbox)
)
def analyze_latest_task(self, attempt_id: str, kind: str) -> dict:
    """
    Mailbox variant: the message carries only (attempt, kind). The payload is
    claimed from Redis at execution time, so it is always the NEWEST frame the
    student sent — older ones that arrived while this task waited were
    overwritten (coalesced), not queued.
    """
    from app.core import frame_mailbox

    payload = frame_mailbox.take(kind, attempt_id)
    if payload is None:
        return {"skipped": True}     # already claimed by a sibling task, or expired
    try:
        if kind == "frame":
            return _analyze_frame_bytes(attempt_id, payload)
        return _analyze_audio_bytes(attempt_id, payload)
    except Exception:
        logger.exception("analyze_latest_task failed for attempt %s (%s)", attempt_id, kind)
        return {"error": True}


def _analyze_frame_bytes(attempt_id: str, image_bytes: bytes) -> dict:
    from app.ai_monitor import snapshot

    result = _get_face_detector().analyze_frame(image_bytes)
    if result.get("flags"):
        snapshot.attach_snapshots(image_bytes, result["flags"])
        _persist_flags(attempt_id, result["flags"])
    return result


def _analyze_audio_bytes(attempt_id: str, audio_bytes: bytes) -> dict:
    result = _get_audio_analyzer().analyze_audio(audio_bytes)
    if result.get("flags"):
        flags_as_dicts = [
            {"type": f, "severity": result.get("severity", "medium"), "message": f}
            for f in result["flags"]
        ]
        _persist_flags(attempt_id, flags_as_dicts)
    return result


# ── Helper ─────────────────────────────────────────────────────────────────────

def _persist_flags(attempt_id: str, flags: list):
    """
    Persist cheat flags AND apply the health penalty in the worker process.

    Delegates to the shared ``app.ai_monitor.health.record_violations`` writer
    so the async (Celery) path decrements health exactly like the sync path —
    previously face/gaze/mouth flags never affected health when the worker ran.
    """
    from app.ai_monitor import health, smoothing
    from app.models.proctoring_settings import ProctoringSettings

    # Temporal smoothing: drop transient single-frame flags before they cost HP.
    flags = smoothing.confirmed_flags(attempt_id, flags)
    if not flags:
        return

    db = SessionLocal()
    try:
        attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
        if not attempt:
            return

        ps = db.query(ProctoringSettings).filter(
            ProctoringSettings.exam_id == attempt.exam_id
        ).first()

        health.record_violations(db, attempt, flags, ps=ps, event_type="frame_analysis")
    except Exception:
        db.rollback()
        logger.exception("_persist_flags failed for attempt %s", attempt_id)
    finally:
        db.close()
