"""
Celery application configuration for Quizzie.

WINDOWS DEVELOPMENT NOTE
========================
Celery's default multiprocessing pool (billiard) does NOT work on Windows
due to WinError 5 (Access Denied) semaphore errors in spawned processes.

Fix: use --pool=solo when starting workers on Windows.

  # Evaluation worker (Windows-safe)
  celery -A app.worker.celery_app worker -Q evaluation --pool=solo --loglevel=info

  # Proctoring worker (Windows-safe)
  celery -A app.worker.celery_app worker -Q proctoring --pool=solo --loglevel=info

On Linux/Mac (production) use the default prefork pool:
  celery -A app.worker.celery_app worker -Q evaluation --concurrency=2 --loglevel=info

REDIS NOTE
==========
Redis does not run natively on Windows. Use one of:
  1. WSL2:  wsl sudo service redis-server start
  2. Docker: docker run -d -p 6379:6379 redis:7-alpine
  3. Memurai (Windows Redis port): https://www.memurai.com

The app is coded to fall back to synchronous evaluation when Redis/Celery
is unavailable, so development works without Redis.
"""
from celery import Celery
from app.core.config import settings
import sys

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

    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    task_track_started=True,

    # Timeouts
    task_soft_time_limit=30,
    task_time_limit=45,

    # ── Windows-safe pool ────────────────────────────────────────────────────
    # billiard's prefork pool crashes on Windows with WinError 5 (semaphore
    # permission denied).  'solo' runs tasks inline in the worker process —
    # single-threaded but works perfectly on Windows for development.
    # On Linux/Mac in production, remove these two lines (prefork is faster).
    **({
        "worker_pool": "solo",
    } if sys.platform == "win32" else {}),

    # ── Broker connection settings ───────────────────────────────────────────
    # Short timeouts so the app doesn't hang when Redis is unavailable.
    broker_connection_retry_on_startup=True,
    broker_connection_max_retries=3,          # give up after 3 retries, not 100
    broker_transport_options={
        "socket_connect_timeout": 3,           # 3 s to connect (was ~120 s default)
        "socket_timeout": 5,
    },
    result_backend_transport_options={
        "socket_connect_timeout": 3,
        "socket_timeout": 5,
    },
)
