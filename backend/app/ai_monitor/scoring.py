"""
Single source of truth for proctoring flag scoring.

Previously three separate, disagreeing tables lived in:
  - ai_monitor/processor.py        (severity_weights)
  - api/v1/enhanced_monitoring.py  (HealthCalculator.PENALTIES + suspicion FLAG_W)

They used inconsistent flag-type names (``no_face`` vs ``no_face_detected``)
and inconsistent severity parsing (``'HIGH'`` vs ``'high'``), which silently
broke the severity multiplier and the suspicion severity term.

Everything now funnels through this module:
  - ``canonical_flag()``  normalises any historical flag name.
  - ``normalize_severity()`` always returns one of 'low' | 'medium' | 'high'.
  - ``health_penalty()`` and ``suspicion_weight()`` are the only weight lookups.
"""
from __future__ import annotations

from typing import Iterable

# ── Canonical flag types ───────────────────────────────────────────────────────
NO_FACE            = "no_face"
MULTIPLE_FACES     = "multiple_faces"
LOOKING_AWAY       = "looking_away"
LOOKING_DOWN       = "looking_down"
GAZE_OFF_SCREEN    = "gaze_off_screen"
MOUTH_MOVEMENT     = "mouth_movement"
FACE_TRACKING_LOST = "face_tracking_lost"
TAB_SWITCH         = "tab_switch"
FULLSCREEN_EXIT    = "fullscreen_exit"
LOUD_NOISE         = "loud_noise"
MULTIPLE_VOICES    = "multiple_voices"
EXCESSIVE_MOVEMENT = "excessive_movement"
COPY_PASTE         = "copy_paste"
MULTI_MONITOR      = "multi_monitor"

# Historical / frontend aliases → canonical name.
_ALIASES = {
    "no_face_detected": NO_FACE,
    "no_face": NO_FACE,
    "multiple_faces_detected": MULTIPLE_FACES,
    "multiple_faces": MULTIPLE_FACES,
    "looking_away": LOOKING_AWAY,
    "head_turned": LOOKING_AWAY,
    "looking_down": LOOKING_DOWN,
    "head_down": LOOKING_DOWN,
    "gaze_off_screen": GAZE_OFF_SCREEN,
    "mouth_movement_detected": MOUTH_MOVEMENT,
    "mouth_movement": MOUTH_MOVEMENT,
    "mouth_open": MOUTH_MOVEMENT,
    "face_tracking_lost": FACE_TRACKING_LOST,
    "tab_switch": TAB_SWITCH,
    "fullscreen_exit": FULLSCREEN_EXIT,
    "loud_noise_detected": LOUD_NOISE,
    "loud_noise": LOUD_NOISE,
    "suspicious_audio": LOUD_NOISE,
    "multiple_voices_detected": MULTIPLE_VOICES,
    "multiple_voices": MULTIPLE_VOICES,
    "excessive_movement": EXCESSIVE_MOVEMENT,
    "copy_paste_attempt": COPY_PASTE,
    "copy_paste": COPY_PASTE,
    "multi_monitor_detected": MULTI_MONITOR,
    "multi_monitor": MULTI_MONITOR,
}

# ── Health penalty (HP removed per violation, before severity multiplier) ───────
_HEALTH_PENALTIES = {
    NO_FACE: 10,
    MULTIPLE_FACES: 15,
    LOOKING_AWAY: 5,
    LOOKING_DOWN: 6,
    GAZE_OFF_SCREEN: 5,
    MOUTH_MOVEMENT: 4,
    FACE_TRACKING_LOST: 5,
    TAB_SWITCH: 7,
    FULLSCREEN_EXIT: 10,
    LOUD_NOISE: 3,
    MULTIPLE_VOICES: 8,
    EXCESSIVE_MOVEMENT: 2,
    COPY_PASTE: 8,
    MULTI_MONITOR: 6,
}
_DEFAULT_HEALTH_PENALTY = 5

# ── Suspicion weight (how indicative of cheating, used by suspicion score) ──────
_SUSPICION_WEIGHTS = {
    MULTIPLE_FACES: 15,
    TAB_SWITCH: 12,
    FULLSCREEN_EXIT: 10,
    COPY_PASTE: 8,
    NO_FACE: 8,
    LOOKING_DOWN: 6,
    MULTI_MONITOR: 6,
    MULTIPLE_VOICES: 6,
    GAZE_OFF_SCREEN: 5,
    LOOKING_AWAY: 4,
    MOUTH_MOVEMENT: 4,
    FACE_TRACKING_LOST: 3,
    LOUD_NOISE: 3,
    EXCESSIVE_MOVEMENT: 2,
}
_DEFAULT_SUSPICION_WEIGHT = 2

# ── Severity ────────────────────────────────────────────────────────────────────
_SEVERITY_MULTIPLIER = {"low": 0.5, "medium": 1.0, "high": 1.5}
_SEVERITY_NUMERIC = {"low": 1, "medium": 3, "high": 8}


def canonical_flag(flag_type) -> str:
    """Map any historical/frontend flag name to its canonical form."""
    key = str(flag_type or "").strip().lower()
    return _ALIASES.get(key, key)


def normalize_severity(value) -> str:
    """
    Coerce any severity representation to 'low' | 'medium' | 'high'.

    Handles plain strings ('high'), Enum members, and the stringified enum
    form 'CheatSeverity.HIGH' that used to silently break multiplier lookups.
    """
    if value is None:
        return "medium"
    # Enum member with a .value attribute
    val = getattr(value, "value", value)
    s = str(val).strip().lower()
    if "." in s:                       # 'cheatseverity.high' → 'high'
        s = s.rsplit(".", 1)[-1]
    if s in _SEVERITY_MULTIPLIER:
        return s
    return "medium"


def severity_multiplier(severity) -> float:
    return _SEVERITY_MULTIPLIER[normalize_severity(severity)]


def severity_numeric(severity) -> int:
    return _SEVERITY_NUMERIC[normalize_severity(severity)]


def health_penalty(flag_type, severity="medium") -> int:
    """HP to remove for one violation, including the severity multiplier."""
    base = _HEALTH_PENALTIES.get(canonical_flag(flag_type), _DEFAULT_HEALTH_PENALTY)
    return int(round(base * severity_multiplier(severity)))


def suspicion_weight(flag_type) -> int:
    return _SUSPICION_WEIGHTS.get(canonical_flag(flag_type), _DEFAULT_SUSPICION_WEIGHT)


def total_suspicion_weight(flags: Iterable) -> float:
    """Sum of (flag weight × severity numeric) for an iterable of (type, sev)."""
    return float(sum(suspicion_weight(t) * severity_numeric(s) for t, s in flags))
