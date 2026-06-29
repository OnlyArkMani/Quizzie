"""
Temporal smoothing for proctoring flags.

Visual detections (gaze off-screen, looking away/down, mouth movement) are
noisy frame to frame — a single glance at the keyboard or a yawn used to flag
instantly. This module requires a flag type to persist across a few consecutive
analyses within a short window before it is "confirmed" and allowed to penalise
health, sharply cutting false positives.

State is kept per worker process (a simple in-memory dict). For a given attempt
frames almost always route to one worker, so this is consistent in practice;
worst case is a one-frame delay in confirming a violation. Hard violations
(multiple faces, no face) use a threshold of 1 so they fire immediately.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List

from app.ai_monitor import scoring

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
_MAX_ATTEMPTS_TRACKED = 5000    # crude cap so the dict can't grow unbounded

_state: Dict[str, Dict[str, list]] = {}
_lock = threading.Lock()


def _threshold(flag_type: str) -> int:
    return _THRESHOLDS.get(scoring.canonical_flag(flag_type), _DEFAULT_THRESHOLD)


def confirm(attempt_id: str, flag_type: str, now: float | None = None) -> bool:
    """
    Record one sighting of ``flag_type`` for ``attempt_id`` and return True when
    enough sightings have accumulated within the window (i.e. the flag is real).
    On confirmation the counter resets so penalties don't fire every frame.
    """
    now = now if now is not None else time.time()
    canonical = scoring.canonical_flag(flag_type)
    threshold = _threshold(canonical)
    if threshold <= 1:
        return True

    with _lock:
        if len(_state) > _MAX_ATTEMPTS_TRACKED:
            _state.clear()
        per_attempt = _state.setdefault(attempt_id, {})
        stamps = [t for t in per_attempt.get(canonical, []) if now - t <= _WINDOW_SECONDS]
        stamps.append(now)
        if len(stamps) >= threshold:
            per_attempt[canonical] = []      # reset after confirming
            return True
        per_attempt[canonical] = stamps
        return False


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
    with _lock:
        _state.pop(attempt_id, None)
