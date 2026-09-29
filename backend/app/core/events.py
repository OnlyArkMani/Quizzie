"""
Cross-process fan-out of proctoring health updates via Redis pub/sub.

Problem this solves
-------------------
A student's WebSocket is held by ONE API process. But the code that changes
their health runs in many places:
  * a Celery proctoring worker (camera/audio frames)  — a different process
  * any API replica handling /violation or /recover   — maybe a different box
The old in-memory ``ConnectionManager.send(...)`` could only reach sockets in
the *same* process, so camera violations never reached the live health bar.

Design
------
Writers publish ``{"attempt_id", "type", "data", ...}`` on one channel. Every
API process runs one subscriber task (``run_subscriber``) and forwards each
message to the sockets it holds locally for that attempt; the others ignore it.

  worker / replica A ──PUBLISH──► Redis ──► replica A subscriber ─► (no socket)
                                        └─► replica B subscriber ─► student's WS

Delivery is at-most-once (pub/sub has no persistence). That is acceptable
because each message is a *full health snapshot*, not a delta: a dropped
message is corrected by the next one, by the snapshot sent on WS (re)connect,
and by the HealthBar's periodic poll of the persisted value. If these were
deltas we'd need Redis Streams / a durable queue instead.

Without Redis (local dev) we deliver in-process only, which is exactly the old
behaviour.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Awaitable, Callable, Dict, Optional

from app.core import redis_client

logger = logging.getLogger(__name__)

HEALTH_CHANNEL = "quizzie:proctoring:health"

# In-process delivery hook, registered by the API process at startup.
_local_dispatch: Optional[Callable[[Dict], None]] = None


def set_local_dispatcher(fn: Optional[Callable[[Dict], None]]) -> None:
    global _local_dispatch
    _local_dispatch = fn


def build_message(attempt_id: str, health: Dict, auto_submitted: bool = False,
                  alert: Optional[Dict] = None) -> Dict:
    return {
        "attempt_id": str(attempt_id),
        "type": "health_update",
        "data": health,
        "auto_submitted": bool(auto_submitted),
        "alert": alert,
    }


def publish(message: Dict) -> bool:
    """Publish to all API processes. Returns True if it went through Redis."""
    client = redis_client.get_sync_redis()
    if client is not None:
        try:
            client.publish(HEALTH_CHANNEL, json.dumps(message, default=str))
            return True
        except Exception as e:
            logger.warning("Redis publish failed (%s); delivering locally only", e)
            redis_client.mark_failed()
    if _local_dispatch is not None:
        _local_dispatch(message)
    return False


# ── Health read model ────────────────────────────────────────────────────────
# Every health change also overwrites a snapshot in Redis, so the students'
# periodic GET /health (≈ 330 req/s at 5k students) is served without touching
# Postgres. Postgres stays the source of truth; the snapshot is a projection.
SNAPSHOT_TTL_SECONDS = 4 * 3600


def snapshot_key(attempt_id: str) -> str:
    return f"attempt:{attempt_id}:health"


def _snapshot_payload(owner_id, health: Dict) -> str:
    return json.dumps({"owner": str(owner_id) if owner_id else None, "data": health}, default=str)


def write_snapshot(attempt_id: str, owner_id, health: Dict, only_if_absent: bool = False) -> None:
    """
    ``only_if_absent`` is for filling the cache after a DB read: a fill must
    never overwrite a newer snapshot written by a concurrent health change
    (read-old / publish-new / write-old would pin a stale value).
    """
    client = redis_client.get_sync_redis()
    if client is None:
        return
    try:
        client.set(snapshot_key(attempt_id), _snapshot_payload(owner_id, health),
                   ex=SNAPSHOT_TTL_SECONDS, nx=only_if_absent)
    except Exception:
        redis_client.mark_failed()


def publish_health(attempt_id: str, health: Dict, auto_submitted: bool = False,
                   alert: Optional[Dict] = None, owner_id=None) -> bool:
    write_snapshot(attempt_id, owner_id, health)
    return publish(build_message(attempt_id, health, auto_submitted, alert))


async def run_subscriber(
    on_message: Callable[[Dict], Awaitable[None]],
    stop: asyncio.Event,
) -> None:
    """
    Long-running task in each API process. Reconnects with capped exponential
    backoff; never raises (a crashed subscriber would silently stop all
    real-time updates for that replica).
    """
    from app.core.cache import cache

    backoff = 0.5
    while not stop.is_set():
        client = cache.raw_client
        if client is None:
            await _sleep_or_stop(stop, 5)
            continue
        pubsub = client.pubsub()
        try:
            await pubsub.subscribe(HEALTH_CHANNEL)
            backoff = 0.5
            while not stop.is_set():
                msg = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if msg is None:
                    continue
                try:
                    payload = json.loads(msg["data"])
                    await on_message(payload)
                except Exception:
                    logger.exception("Bad proctoring event dropped")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Proctoring subscriber error (%s); reconnecting in %.1fs", e, backoff)
            await _sleep_or_stop(stop, backoff)
            backoff = min(backoff * 2, 10)
        finally:
            try:
                await pubsub.reset()
            except Exception:
                pass


async def _sleep_or_stop(stop: asyncio.Event, seconds: float) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass
