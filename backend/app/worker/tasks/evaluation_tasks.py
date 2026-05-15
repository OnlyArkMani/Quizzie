"""
Celery task for exam evaluation.
Runs score calculation off the web process for large exams.
"""
import logging
from uuid import UUID

from app.worker.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.evaluation_service import EvaluationService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.worker.tasks.evaluation_tasks.evaluate_attempt_task",
    bind=True,
    max_retries=3,
    default_retry_delay=5,
)
def evaluate_attempt_task(self, attempt_id: str) -> dict:
    """
    Evaluate a submitted exam attempt.
    Called asynchronously after /submit so the HTTP response is instant.
    """
    db = SessionLocal()
    try:
        svc = EvaluationService(db)
        result = svc.evaluate_attempt(UUID(attempt_id))
        logger.info("Evaluated attempt %s → score %.1f%%", attempt_id, result["score"])
        return result
    except Exception as exc:
        db.rollback()
        logger.exception("evaluate_attempt_task failed for %s", attempt_id)
        raise self.retry(exc=exc)
    finally:
        db.close()
