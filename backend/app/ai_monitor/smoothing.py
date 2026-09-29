"""
Temporal smoothing for proctoring flags.

Visual detections (gaze off-screen, looking away/down, mouth movement) are
noisy frame to frame — a single glance at the keyboard or a yawn used to flag
instantly. A flag type must be sighted ``threshold`` times within a short
window before it is "confirmed" and allowed to penalise health, sharply
cutting false positives. Hard violations (multiple faces) use threshold 1.

State lives in Redis (sorted-set sliding window, see app.core.rate_limit), so
it is shared by every Celery worker process. It used to be a per-process dict:
with ``--concurrency=4`` consecutive frames of one attempt land on different
processes, each seeing only ~1/4 of the sightings, so a real sustained
violation could go unconfirmed. Falls back to in-process state without Redis.
"""
from __future__ import annotations

from typing import List

from app.ai_monitor import scoring
from app.core import rate_limit, redis_client

# How many consecutive sightings (within the window) confirm a flag.
# looking_down is deliberately high so only a *prolonged* head-down (not a
# keyboard glance) is ever penalised — see FaceDetector pitch handling.
_THRESHOLDS = {
    scoring.LOOKING_AWAY: 2,
    scoring.LOOKING_DOWN: 4,
    scoring.GAZE_OFF_SCREEN: 2,
    scoring.MOUTH_MOVEMENT: 3,
    scoring.LOUD_NOISE: 2,
    scoring.NO_FACE: 2,
}
_DEFAULT_THRESHOLD = 1          # multiple_faces, tab_switch, etc. fire at once
_WINDOW_SECONDS = 12.0          # sightings older than this are forgotten

def _threshold(flag_type: str) -> int:
    return _THRESHOLDS.get(scoring.canonical_flag(flag_type), _DEFAULT_THRESHOLD)


def confirm(attempt_id: str, flag_type: str, now: float | None = None) -> bool:
    """
    Record one sighting of ``flag_type`` for ``attempt_id`` and return True when
    enough sightings have accumulated within the window (i.e. the flag is real).
    On confirmation the counter resets so penalties don't fire every frame.
    (``now`` is accepted for backwards compatibility; the window uses Redis time.)
    """
    canonical = scoring.canonical_flag(flag_type)
    return rate_limit.hit_and_check_sync(
        f"{attempt_id}:{canonical}", _threshold(canonical), _WINDOW_SECONDS
    )


def confirmed_flags(attempt_id: str, flags: List) -> List:
    """
    Filter a list of flag dicts/strings, returning only those confirmed by
    temporal smoothing. Non-confirmed flags are dropped (treated as transient).
    """
    out = []
    for flag in flags or []:
        flag_type = flag.get("type") if isinstance(flag, dict) else flag
        if confirm(attempt_id, flag_type):
            out.append(flag)
    return out


def reset(attempt_id: str) -> None:
    """Forget all smoothing state for an attempt (e.g. on submit)."""
    client = redis_client.get_sync_redis()
    if client is not None:
        try:
            keys = [f"sm:{attempt_id}:{scoring.canonical_flag(t)}" for t in _THRESHOLDS]
            client.delete(*keys)
        except Exception:
            redis_client.mark_failed()
