"""
Distributed sliding-window counters on Redis.

Used for two things that previously lived in per-process Python dicts (and so
silently broke as soon as there was more than one API replica or Celery
worker process):

  * rate limiting proctoring uploads            — ``allow`` / ``allow_sync``
  * temporal smoothing of proctoring detections  — ``hit_and_check_sync``

Algorithm: sliding-window *log*. Each event is a member of a sorted set scored
by its timestamp. To decide, we drop members older than the window, count the
rest, and compare with the limit. All of it runs as ONE Lua script, so the
check-then-add is atomic across every replica (no two requests can both see
"7 of 8" and both get in).

Timestamps come from ``redis.call('TIME')`` — Redis's clock — so API replicas
with skewed clocks still agree on what "the last 5 seconds" means.

Why a log and not a fixed-window INCR counter? A fixed window lets a client
burst 2x the limit across a window boundary (8 at 4.9 s + 8 at 5.1 s). The log
is exact. Its cost is O(limit) memory per key, which is tiny here (limit ≈ 8).

If Redis is down we fall back to an in-process sliding window: still protects
each process (degraded, not disabled), and the API keeps working.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from typing import Deque, Dict

from app.core import redis_client

# KEYS[1]=key  ARGV[1]=window_ms  ARGV[2]=limit  ARGV[3]=unique member
# Returns 1 if the event is admitted (and recorded), else 0.
_ALLOW_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
  return 0
end
redis.call('ZADD', KEYS[1], now, ARGV[3])
redis.call('PEXPIRE', KEYS[1], window)
return 1
"""

# Record a sighting; return 1 (and reset) once `threshold` sightings fall
# inside the window. Used for flag smoothing.
_HIT_LUA = """
local t = redis.call('TIME')
local now = tonumber(t[1]) * 1000 + math.floor(tonumber(t[2]) / 1000)
local window = tonumber(ARGV[1])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
redis.call('ZADD', KEYS[1], now, ARGV[3])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[2]) then
  redis.call('DEL', KEYS[1])
  return 1
end
redis.call('PEXPIRE', KEYS[1], window)
return 0
"""


# ── In-process fallback (per process; used only when Redis is unreachable) ───

class _LocalWindows:
    MAX_KEYS = 10_000

    def __init__(self):
        self._d: Dict[str, Deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float, window: float) -> Deque[float]:
        dq = self._d.setdefault(key, deque())
        while dq and now - dq[0] > window:
            dq.popleft()
        if len(self._d) > self.MAX_KEYS:
            self._d = {k: v for k, v in self._d.items() if v and now - v[-1] <= 60}
            self._d.setdefault(key, dq)
        return dq

    def allow(self, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._prune(key, now, window)
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True

    def hit(self, key: str, threshold: int, window: float) -> bool:
        now = time.monotonic()
        with self._lock:
            dq = self._prune(key, now, window)
            dq.append(now)
            if len(dq) >= threshold:
                dq.clear()
                return True
            return False

    def clear(self):
        with self._lock:
            self._d.clear()


_local = _LocalWindows()


def _member() -> str:
    return uuid.uuid4().hex


# ── Public API ────────────────────────────────────────────────────────────────

async def allow(key: str, limit: int, window_seconds: float) -> bool:
    """Async (event-loop) variant, uses the shared async Redis pool."""
    from app.core.cache import cache

    client = cache.raw_client
    if client is not None:
        try:
            ok = await client.eval(
                _ALLOW_LUA, 1, f"rl:{key}", int(window_seconds * 1000), limit, _member()
            )
            return bool(ok)
        except Exception:
            pass
    return _local.allow(key, limit, window_seconds)


def allow_sync(key: str, limit: int, window_seconds: float) -> bool:
    client = redis_client.get_sync_redis()
    if client is not None:
        try:
            return bool(client.eval(
                _ALLOW_LUA, 1, f"rl:{key}", int(window_seconds * 1000), limit, _member()
            ))
        except Exception:
            redis_client.mark_failed()
    return _local.allow(key, limit, window_seconds)


def hit_and_check_sync(key: str, threshold: int, window_seconds: float) -> bool:
    """Record one sighting; True once `threshold` sightings are in the window."""
    if threshold <= 1:
        return True
    client = redis_client.get_sync_redis()
    if client is not None:
        try:
            return bool(client.eval(
                _HIT_LUA, 1, f"sm:{key}", int(window_seconds * 1000), threshold, _member()
            ))
        except Exception:
            redis_client.mark_failed()
    return _local.hit(key, threshold, window_seconds)


def reset_local_for_tests() -> None:
    _local.clear()
