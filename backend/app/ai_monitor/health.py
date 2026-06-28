"""
Centralised proctoring-health logic — the single place that mutates health.

Why this exists:
  * Health used to be recomputed from the entire cheat_log history on every
    request (O(n) per call, O(n^2) over an exam) and recovery never persisted.
  * The web "sync" path, the Celery worker, and the client-driven /violation
    endpoint each applied health differently, so face/gaze/mouth flags only
    affected health on the sync path. Now every path calls ``record_violations``
    here, which writes the cheat logs AND decrements the persisted
    ``ExamAttempt.current_health`` column in one transaction.

All weights/severity handling come from ``app.ai_monitor.scoring`` so health,
suspicion scoring, and the processor agree on one table.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.ai_monitor import scoring
from app.models.attempt import ExamAttempt, AttemptStatus
from app.models.cheat_log import CheatLog, CheatSeverity

logger = logging.getLogger(__name__)

DEFAULT_INITIAL_HEALTH = 100


def initial_health(ps) -> int:
    """Initial/max health for an attempt, from proctoring settings (or default)."""
    return getattr(ps, "initial_health", None) or DEFAULT_INITIAL_HEALTH


def health_status(current: int, maximum: int, violations_count: int = 0) -> Dict:
    """Build the health-status payload sent to the frontend / WebSocket."""
    maximum = maximum or DEFAULT_INITIAL_HEALTH
    current = max(0, min(current, maximum))
    pct = (current / maximum) * 100 if maximum > 0 else 0
    if pct > 70:
        s = "good"
    elif pct > 40:
        s = "warning"
    elif pct > 0:
        s = "critical"
    else:
        s = "failed"
    return {
        "current": current,
        "max": maximum,
        "percentage": pct,
        "status": s,
        "violations_count": violations_count,
    }


def ensure_health(attempt: ExamAttempt, ps) -> int:
    """
    Lazily initialise ``attempt.current_health`` for older rows where the
    column is still NULL, returning the effective current health.
    """
    if attempt.current_health is None:
        attempt.current_health = initial_health(ps)
    return attempt.current_health


def _coerce_flag(flag, default_severity: str) -> Dict:
    """Normalise a flag (string or dict) into {type, severity, message, metadata}."""
    if isinstance(flag, dict):
        return {
            "type": flag.get("type", "unknown"),
            "severity": scoring.normalize_severity(flag.get("severity", default_severity)),
            "message": flag.get("message", ""),
            "metadata": flag.get("metadata") or {},
        }
    return {
        "type": str(flag),
        "severity": scoring.normalize_severity(default_severity),
        "message": str(flag).replace("_", " "),
        "metadata": {},
    }


def record_violations(
    db: Session,
    attempt: ExamAttempt,
    flags: List,
    ps=None,
    event_type: Optional[str] = None,
    default_severity: str = "medium",
    commit: bool = True,
) -> Dict:
    """
    The single write path for proctoring violations.

    Persists one CheatLog per flag, decrements the persisted health column by
    the shared health penalty, bumps the violation counter, and auto-submits
    when health hits zero (if enabled). Returns a summary dict including the
    fresh health status so callers can push it over the WebSocket.
    """
    maximum = initial_health(ps)
    current = ensure_health(attempt, ps)

    logged = 0
    for raw in flags or []:
        flag = _coerce_flag(raw, default_severity)
        canonical = scoring.canonical_flag(flag["type"])

        try:
            severity_enum = CheatSeverity(flag["severity"])
        except ValueError:
            severity_enum = CheatSeverity.MEDIUM

        meta = {"message": flag["message"]}
        if event_type:
            meta["event_type"] = event_type
        if flag["metadata"]:
            meta.update(flag["metadata"])

        db.add(CheatLog(
            attempt_id=attempt.id,
            flag_type=canonical,
            severity=severity_enum,
            timestamp=datetime.now(timezone.utc),
            meta_data=meta,
        ))

        current = max(0, current - scoring.health_penalty(canonical, flag["severity"]))
        logged += 1

    attempt.current_health = current
    attempt.cheating_flags = (attempt.cheating_flags or 0) + logged

    auto_submitted = False
    auto_submit_enabled = getattr(ps, "auto_submit_on_zero_health", True)
    if current <= 0 and auto_submit_enabled:
        status_val = attempt.status.value if hasattr(attempt.status, "value") else attempt.status
        if status_val == AttemptStatus.IN_PROGRESS.value:
            attempt.status = AttemptStatus.SUBMITTED
            attempt.submitted_at = datetime.now(timezone.utc)
            auto_submitted = True

    if commit:
        db.commit()

    return {
        "logged": logged,
        "auto_submitted": auto_submitted,
        "health": health_status(current, maximum, _violation_count(db, attempt.id)),
    }


def recover(db: Session, attempt: ExamAttempt, amount: int, ps=None, commit: bool = True) -> Dict:
    """Restore up to ``amount`` HP (capped at max). Persists, unlike before."""
    maximum = initial_health(ps)
    current = ensure_health(attempt, ps)
    new_health = min(maximum, current + max(0, amount))
    recovered = new_health - current
    attempt.current_health = new_health
    if commit:
        db.commit()
    return {
        "recovered": recovered,
        "health": health_status(new_health, maximum, _violation_count(db, attempt.id)),
    }


def current_health_status(db: Session, attempt: ExamAttempt, ps=None) -> Dict:
    """Read current health without mutating (lazy-inits NULL rows)."""
    maximum = initial_health(ps)
    current = ensure_health(attempt, ps)
    # ensure_health may have set the column; persist that one-time init.
    if db.is_modified(attempt):
        db.commit()
    return health_status(current, maximum, _violation_count(db, attempt.id))


def recompute_from_logs(db: Session, attempt: ExamAttempt, ps=None) -> int:
    """
    Rebuild health by replaying the cheat log — used only as a backfill/repair
    path, not on the hot request path.
    """
    maximum = initial_health(ps)
    current = maximum
    logs = db.query(CheatLog).filter(CheatLog.attempt_id == attempt.id).all()
    for v in logs:
        current = max(0, current - scoring.health_penalty(v.flag_type, v.severity))
    return current


def _violation_count(db: Session, attempt_id) -> int:
    return db.query(CheatLog).filter(CheatLog.attempt_id == attempt_id).count()
