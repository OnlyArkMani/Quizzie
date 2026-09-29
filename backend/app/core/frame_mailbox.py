"""
Latest-frame mailbox: bounded, self-shedding transport for proctoring uploads.

Problem
-------
Every upload used to become a Celery task carrying the whole image (base64,
+33 %) in the broker. When workers fall behind — and at ~250 frames/s for 500
students they will, see docs/HLD.md §5 — the queue grows without bound:
Redis memory fills (on a 25 MB plan, in seconds), and every frame analysed is
older than the last. A 40-second-old frame is useless for live proctoring.

Design
------
Per (kind, attempt) Redis keeps ONE slot:
    frame:<kind>:<attempt>    latest payload (TTL 10 s — stale frames expire)
    pending:<kind>:<attempt>  "a task for this attempt is queued" (SET NX)

Upload:  SET frame (overwrite)  +  SET pending NX       (one MULTI/EXEC)
         - pending was absent  -> enqueue a tiny task {attempt, kind}
         - pending was present -> nothing to do: the queued task will read
           the newest frame. The older frame was dropped ("coalesced").
Worker:  DEL pending, then GETDEL frame, analyse it.
         (Deleting pending FIRST means a frame arriving mid-analysis enqueues
          a fresh task instead of being stranded; worst case one no-op task.)

Properties
----------
* Broker holds <= 1 queued task per active attempt; Redis holds <= 1 frame per
  attempt. Memory is O(students), not O(backlog).
* Under overload each student is analysed less OFTEN, never LATER: graceful
  degradation (load shedding) instead of an ever-growing, ever-staler queue.
* Coalesced uploads are counted in ``stats:coalesced:<kind>`` so shedding is
  observable.
"""
from __future__ import annotations

from typing import Optional

from app.core import redis_client

FRAME_TTL_SECONDS = 10
PENDING_TTL_SECONDS = 30      # a lost task can't block an attempt for longer

ENQUEUE = "enqueue"
COALESCED = "coalesced"
UNAVAILABLE = "unavailable"


def _frame_key(kind: str, attempt_id: str) -> str:
    return f"frame:{kind}:{attempt_id}"


def _pending_key(kind: str, attempt_id: str) -> str:
    return f"pending:{kind}:{attempt_id}"


def post(kind: str, attempt_id: str, payload: bytes) -> str:
    """Store the newest payload; say whether the caller must enqueue a task."""
    client = redis_client.get_sync_redis(binary=True)
    if client is None:
        return UNAVAILABLE
    try:
        pipe = client.pipeline(transaction=True)
        pipe.set(_frame_key(kind, attempt_id), payload, ex=FRAME_TTL_SECONDS)
        pipe.set(_pending_key(kind, attempt_id), b"1", nx=True, ex=PENDING_TTL_SECONDS)
        _, became_pending = pipe.execute()
        if became_pending:
            return ENQUEUE
        client.incr(f"stats:coalesced:{kind}")
        return COALESCED
    except Exception:
        redis_client.mark_failed()
        return UNAVAILABLE


def cancel_pending(kind: str, attempt_id: str) -> None:
    """Enqueue failed: clear the marker so the next upload retries."""
    client = redis_client.get_sync_redis(binary=True)
    if client is None:
        return
    try:
        client.delete(_pending_key(kind, attempt_id))
    except Exception:
        redis_client.mark_failed()


def take(kind: str, attempt_id: str) -> Optional[bytes]:
    """Worker side: claim the newest payload (None if already taken/expired)."""
    client = redis_client.get_sync_redis(binary=True)
    if client is None:
        return None
    try:
        client.delete(_pending_key(kind, attempt_id))
        return client.getdel(_frame_key(kind, attempt_id))
    except Exception:
        redis_client.mark_failed()
        return None


def coalesced_count(kind: str) -> int:
    client = redis_client.get_sync_redis(binary=True)
    if client is None:
        return 0
    try:
        return int(client.get(f"stats:coalesced:{kind}") or 0)
    except Exception:
        return 0
