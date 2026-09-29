"""
Synchronous Redis client for code that runs outside the event loop
(Celery workers, FastAPI threadpool sections).

The async client in ``app.core.cache`` serves ``async def`` code; this one
serves blocking code. Both point at the same Redis.

Failure policy: Redis is an accelerator here, not the source of truth. If it
is unreachable we return None and callers fall back to process-local
behaviour. To avoid paying a connect timeout on every call while Redis is
down, a failed connect is remembered for ``_RETRY_AFTER`` seconds.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_RETRY_AFTER = 30.0
_client: Optional[redis.Redis] = None
_bin_client: Optional[redis.Redis] = None
_down_until = 0.0
_lock = threading.Lock()


def get_sync_redis(binary: bool = False) -> Optional[redis.Redis]:
    """
    ``binary=True`` returns a client that does NOT decode responses (raw
    bytes), for binary payloads such as webcam frames.
    """
    global _client, _bin_client, _down_until
    existing = _bin_client if binary else _client
    if existing is not None:
        return existing
    if time.monotonic() < _down_until:
        return None
    with _lock:
        existing = _bin_client if binary else _client
        if existing is not None:
            return existing
        try:
            c = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=not binary,
                socket_connect_timeout=1,
                socket_timeout=2,
                health_check_interval=30,
            )
            c.ping()
        except Exception as e:  # pragma: no cover - depends on environment
            logger.warning("Sync Redis unavailable (%s); using local fallbacks for %ss", e, _RETRY_AFTER)
            _down_until = time.monotonic() + _RETRY_AFTER
            return None
        if binary:
            _bin_client = c
        else:
            _client = c
        return c


def mark_failed() -> None:
    """Call after a command fails mid-flight so the next call reconnects."""
    global _client, _bin_client, _down_until
    _client = None
    _bin_client = None
    _down_until = time.monotonic() + _RETRY_AFTER


def reset_for_tests() -> None:
    global _client, _bin_client, _down_until
    _client = None
    _bin_client = None
    _down_until = 0.0
