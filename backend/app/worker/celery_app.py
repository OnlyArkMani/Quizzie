"""
Celery application configuration for Quizzie.

Workers process:
  - AI frame analysis  (proctoring_tasks.analyze_frame_task)
  - AI audio analysis  (proctoring_tasks.analyze_audio_task)
  - Exam evaluation    (evaluation_tasks.evaluate_attempt_task)

Start workers:
  celery -A app.worker.celery_app worker -Q proctoring --concurrency=4 --loglevel=info
  celery -A app.worker.celery_app worker -Q evaluation --concurrency=2 --loglevel=info
"""
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "quizzie",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.worker.tasks.proctoring_tasks",
        "app.worker.tasks.evaluation_tasks",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_routes={
        "app.worker.tasks.proctoring_tasks.*": {"queue": "proctoring"},
        "app.worker.tasks.evaluation_tasks.*": {"queue": "evaluation"},
    },
    # Reliability: only ack after task succeeds — requeue on crash
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # One task per worker at a time (MediaPipe is CPU-bound, prefetch=1 prevents queue bloat)
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_track_started=True,
    task_soft_time_limit=30,
    task_time_limit=45,
)
