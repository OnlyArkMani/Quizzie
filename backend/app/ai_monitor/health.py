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

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.ai_monitor import scoring
from app.core import events
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

    Persists one CheatLog per flag and applies the summed penalty with ONE
    atomic statement:

        UPDATE exam_attempts
        SET current_health = GREATEST(0, COALESCE(current_health, :max) - :penalty),
            cheating_flags = COALESCE(cheating_flags, 0) + :n
        WHERE id = :id
        RETURNING current_health

    Why not read → subtract in Python → write? Because the frame task and the
    audio task for the same attempt run concurrently in different Celery
    workers. Both would read health=100, both would write back 100-penalty, and
    one penalty would silently vanish (a "lost update"). Doing the arithmetic
    inside the UPDATE makes Postgres serialise the two writers on the row lock;
    the second one re-reads the committed value before applying its penalty.

    Auto-submits (compare-and-set, via AttemptService) when health hits zero.
    """
    from app.services.attempt_service import AttemptService

    maximum = initial_health(ps)

    logs = []
    penalty = 0
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

        logs.append(CheatLog(
            attempt_id=attempt.id,
            flag_type=canonical,
            severity=severity_enum,
            timestamp=datetime.now(timezone.utc),
            meta_data=meta,
        ))
        penalty += scoring.health_penalty(canonical, flag["severity"])

    db.add_all(logs)
    current, flag_count = db.execute(
        update(ExamAttempt)
        .where(ExamAttempt.id == attempt.id)
        .values(
            current_health=func.greatest(
                0, func.coalesce(ExamAttempt.current_health, maximum) - penalty
            ),
            cheating_flags=func.coalesce(ExamAttempt.cheating_flags, 0) + len(logs),
        )
        .returning(ExamAttempt.current_health, ExamAttempt.cheating_flags)
        .execution_options(synchronize_session=False)
    ).one()
    db.expire(attempt, ["current_health", "cheating_flags"])

    auto_submitted = False
    auto_submit_enabled = getattr(ps, "auto_submit_on_zero_health", True)
    if current <= 0 and auto_submit_enabled:
        auto_submitted = AttemptService(db).close_for_health(attempt)

    if commit:
        db.commit()
        if auto_submitted:
            from app.services import evaluation_dispatch
            evaluation_dispatch.dispatch(attempt.id)

    # violations_count comes from the counter maintained in the same UPDATE —
    # it used to be a COUNT(*) over cheat_logs on every violation and every
    # health read, i.e. O(violations so far) on the hottest proctoring path.
    status = health_status(current, maximum, flag_count)
    if commit and logs:
        threshold = getattr(ps, "health_warning_threshold", None) or 40
        alert = None
        if status["percentage"] <= threshold:
            alert = {
                "message": f"Health is at {status['percentage']:.0f}%",
                "severity": "high",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        events.publish_health(str(attempt.id), status, auto_submitted=auto_submitted,
                              alert=alert, owner_id=attempt.student_id)

    return {
        "logged": len(logs),
        "auto_submitted": auto_submitted,
        "health": status,
    }


def recover(db: Session, attempt: ExamAttempt, amount: int, ps=None, commit: bool = True) -> Dict:
    """
    Restore up to ``amount`` HP, capped at max, atomically (same lost-update
    reasoning as record_violations). Only in-progress attempts can recover.
    """
    maximum = initial_health(ps)
    before, flag_count = db.execute(
        select(ExamAttempt.current_health, ExamAttempt.cheating_flags).where(ExamAttempt.id == attempt.id)
    ).one()
    before = maximum if before is None else before
    row = db.execute(
        update(ExamAttempt)
        .where(ExamAttempt.id == attempt.id, ExamAttempt.status == AttemptStatus.IN_PROGRESS)
        .values(current_health=func.least(
            maximum, func.coalesce(ExamAttempt.current_health, maximum) + max(0, amount)
        ))
        .returning(ExamAttempt.current_health)
        .execution_options(synchronize_session=False)
    ).first()
    new_health = row[0] if row else before
    db.expire(attempt, ["current_health"])
    if commit:
        db.commit()
    status = health_status(new_health, maximum, flag_count or 0)
    if commit and row:
        events.publish_health(str(attempt.id), status, owner_id=attempt.student_id)
    return {"recovered": max(0, new_health - before), "health": status}


def seconds_since_last_violation(db: Session, attempt_id) -> Optional[float]:
    last = db.execute(
        select(func.max(CheatLog.timestamp)).where(CheatLog.attempt_id == attempt_id)
    ).scalar_one_or_none()
    if last is None:
        return None
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - last).total_seconds()


def current_health_status(db: Session, attempt: ExamAttempt, ps=None) -> Dict:
    """Read current health without mutating (lazy-inits NULL rows)."""
    maximum = initial_health(ps)
    current = ensure_health(attempt, ps)
    # ensure_health may have set the column; persist that one-time init.
    if db.is_modified(attempt):
        db.commit()
    return health_status(current, maximum, attempt.cheating_flags or 0)


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
    """Audit/repair only (O(n)). Hot paths read ExamAttempt.cheating_flags."""
    return db.query(CheatLog).filter(CheatLog.attempt_id == attempt_id).count()
