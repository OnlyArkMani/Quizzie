"""
Getting a closed attempt evaluated exactly once, without the results page
doing the work.

Before: while an attempt was SUBMITTED, every GET /results ran the full
evaluation inline — on every poll, racing the Celery task. When an exam ends
everyone submits at once, the evaluation queue backs up, and each student's
results polling multiplied the work.

Now:
  * every way an attempt closes (submit, deadline, health = 0) calls
    ``dispatch``; a successful enqueue leaves a short-lived marker
    ``eval:pending:<attempt>`` in Redis;
  * GET /results while the marker exists → 202 "evaluating" (cheap);
  * no marker (Celery unavailable, or the task died and the marker expired)
    → evaluate inline, but only the request that wins ``lock:eval:<attempt>``;
    concurrent pollers get 202 instead of duplicating the work.
Evaluation itself is idempotent (it recomputes from stored answers), so the
rare double-run after a marker expires is harmless — just wasted CPU.
"""
from __future__ import annotations

import concurrent.futures
import logging

from app.core import redis_client
from app.core.config import settings

logger = logging.getLogger(__name__)


def _pending_key(attempt_id) -> str:
    return f"eval:pending:{attempt_id}"


def _lock_key(attempt_id) -> str:
    return f"lock:eval:{attempt_id}"


def mark_pending(attempt_id) -> None:
    client = redis_client.get_sync_redis()
    if client is None:
        return
    try:
        client.set(_pending_key(attempt_id), "1", ex=settings.EVAL_PENDING_TTL_SECONDS)
    except Exception:
        redis_client.mark_failed()


def clear_pending(attempt_id) -> None:
    client = redis_client.get_sync_redis()
    if client is None:
        return
    try:
        client.delete(_pending_key(attempt_id))
    except Exception:
        redis_client.mark_failed()


def is_pending(attempt_id) -> bool:
    client = redis_client.get_sync_redis()
    if client is None:
        return False
    try:
        return bool(client.exists(_pending_key(attempt_id)))
    except Exception:
        redis_client.mark_failed()
        return False


def acquire_inline_lock(attempt_id) -> bool:
    """True if this caller should run the inline evaluation now."""
    client = redis_client.get_sync_redis()
    if client is None:
        return True            # no Redis: nothing to coordinate with
    try:
        return bool(client.set(_lock_key(attempt_id), "1", nx=True, ex=30))
    except Exception:
        redis_client.mark_failed()
        return True


def release_inline_lock(attempt_id) -> None:
    client = redis_client.get_sync_redis()
    if client is None:
        return
    try:
        client.delete(_lock_key(attempt_id))
    except Exception:
        redis_client.mark_failed()


def enqueue(task_fn, attempt_id: str) -> str | None:
    """
    apply_async with a hard 5 s cap (a slow-to-refuse broker must never hang the
    caller). Returns the task id, or None if it couldn't be queued.
    """
    if settings.EVALUATION_MODE == "inline" or task_fn is None:
        return None
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            task = pool.submit(
                task_fn.apply_async, args=[attempt_id], kwargs={"queue": "evaluation"}
            ).result(timeout=5)
    except Exception as e:
        logger.warning("Celery unavailable (%s) — evaluation will run inline on demand.", e)
        return None
    mark_pending(attempt_id)
    return task.id


def dispatch(attempt_id) -> str | None:
    """Queue evaluation for an attempt that just closed (deadline / health path)."""
    try:
        from app.worker.tasks.evaluation_tasks import evaluate_attempt_task
    except Exception:
        return None
    return enqueue(evaluate_attempt_task, str(attempt_id))
