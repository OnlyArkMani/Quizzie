"""
Celery tasks for AI proctoring.

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
        image_bytes = base64.b64decode(image_bytes_b64)
        result = _get_face_detector().analyze_frame(image_bytes)

        if result.get("flags"):
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


# ── Helper ─────────────────────────────────────────────────────────────────────

def _persist_flags(attempt_id: str, flags: list):
    """Write cheat flags to DB and increment attempt.cheating_flags counter."""
    db = SessionLocal()
    try:
        attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
        if not attempt:
            return

        for flag in flags:
            if isinstance(flag, dict):
                flag_type = flag.get("type", "unknown")
                raw_severity = flag.get("severity", "low")
            else:
                flag_type = str(flag)
                raw_severity = "low"

            try:
                severity = CheatSeverity(raw_severity)
            except ValueError:
                severity = CheatSeverity.LOW

            db.add(CheatLog(
                attempt_id=attempt.id,
                flag_type=flag_type,
                severity=severity,
                meta_data={"message": flag.get("message", "") if isinstance(flag, dict) else ""},
            ))

        attempt.cheating_flags = (attempt.cheating_flags or 0) + len(flags)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("_persist_flags failed for attempt %s", attempt_id)
    finally:
        db.close()
