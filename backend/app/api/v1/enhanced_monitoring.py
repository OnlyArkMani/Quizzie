"""
Enhanced Proctoring API Endpoints
Handles real-time monitoring, health tracking, and configuration
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, Query
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Set
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import UUID
import asyncio
import logging
from collections import defaultdict

from app.core.database import get_db, run_db, SessionLocal
from app.api.deps import get_current_user
from app.core.security import decode_access_token
from app.models.user import User
from app.models.attempt import ExamAttempt, AttemptStatus
from app.models.cheat_log import CheatLog, CheatSeverity
from app.models.exam import Exam
# Import with alias to avoid name conflict with the Pydantic schema below
from app.models.proctoring_settings import ProctoringSettings as ProctoringSettingsModel
from app.ai_monitor import scoring, health as health_mod
from app.core import events, rate_limit
from app.core.cache import cache

logger = logging.getLogger(__name__)

router = APIRouter()


# WebSocket connection manager for real-time updates
class ConnectionManager:
    """
    Sockets held by THIS process, keyed by attempt id. Several sockets can
    watch one attempt (the student plus an examiner) — the old
    one-socket-per-attempt dict let an examiner connection silently replace
    the student's.

    Messages arrive via ``dispatch`` from the Redis subscriber (see
    app.core.events), so an update produced by a Celery worker or another
    replica still reaches a socket connected here.
    """

    def __init__(self):
        self._sockets: Dict[str, Set[WebSocket]] = defaultdict(set)
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, attempt_id: str, websocket: WebSocket):
        await websocket.accept()
        self._sockets[attempt_id].add(websocket)

    def disconnect(self, attempt_id: str, websocket: Optional[WebSocket] = None):
        socks = self._sockets.get(attempt_id)
        if not socks:
            return
        if websocket is None:
            socks.clear()
        else:
            socks.discard(websocket)
        if not socks:
            self._sockets.pop(attempt_id, None)

    def local_connections(self, attempt_id: str) -> int:
        return len(self._sockets.get(attempt_id, ()))

    async def dispatch(self, message: dict) -> int:
        """Deliver an event to the local sockets for its attempt. Returns #sent."""
        attempt_id = message.get("attempt_id")
        sent = 0
        for ws in list(self._sockets.get(attempt_id, ())):
            try:
                await ws.send_json({"type": "health_update", "data": message.get("data")})
                if message.get("alert"):
                    await ws.send_json({"type": "violation_alert", "data": message["alert"]})
                if message.get("auto_submitted"):
                    await ws.send_json({"type": "auto_submitted", "data": {"attempt_id": attempt_id}})
                sent += 1
            except Exception:
                self.disconnect(attempt_id, ws)
        return sent

    def dispatch_threadsafe(self, message: dict) -> None:
        """In-process fallback when Redis is down (called from worker threads)."""
        if self._loop is not None and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.dispatch(message), self._loop)


manager = ConnectionManager()


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class ExamProctoringConfig(BaseModel):
    """Proctoring configuration settings for an exam"""
    camera_enabled: bool = True
    microphone_enabled: bool = True
    face_detection_enabled: bool = True
    multiple_face_detection: bool = True
    head_pose_detection: bool = True
    tab_switch_detection: bool = True
    min_face_confidence: float = Field(0.6, ge=0.0, le=1.0)
    max_head_rotation: float = Field(30.0, ge=0.0, le=180.0)
    detection_interval: int = Field(2, ge=1, le=60)
    initial_health: int = Field(100, ge=1, le=200)
    auto_submit_on_zero_health: bool = True
    health_warning_threshold: int = Field(40, ge=0, le=100)


class ViolationFlag(BaseModel):
    """Individual violation flag"""
    type: str
    severity: str  # 'low', 'medium', 'high'
    message: str
    metadata: Optional[dict] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HealthUpdate(BaseModel):
    """Health status update"""
    current_health: int
    max_health: int
    health_percentage: float
    status: str  # 'good', 'warning', 'critical', 'failed'
    last_violation: Optional[ViolationFlag] = None


class ProctoringEvent(BaseModel):
    """Proctoring event from frontend"""
    attempt_id: UUID
    event_type: str  # 'frame_analysis', 'tab_switch', 'audio_detection'
    flags: List[dict]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    frame_data: Optional[str] = None  # Base64 encoded image


# ─── API Endpoints ────────────────────────────────────────────────────────────

@router.post("/exam/{exam_id}/proctoring-settings")
def update_proctoring_settings(
    exam_id: UUID,
    settings: ExamProctoringConfig,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update proctoring settings for an exam (Examiner only)"""
    if current_user.role not in ['examiner', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only examiners can update proctoring settings"
        )

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    if str(exam.created_by) != str(current_user.id) and current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this exam"
        )

    # Upsert proctoring settings row
    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == exam_id
    ).first()

    if ps is None:
        ps = ProctoringSettingsModel(exam_id=exam_id)
        db.add(ps)

    ps.camera_enabled = settings.camera_enabled
    ps.microphone_enabled = settings.microphone_enabled
    ps.face_detection_enabled = settings.face_detection_enabled
    ps.multiple_face_detection = settings.multiple_face_detection
    ps.head_pose_detection = settings.head_pose_detection
    ps.tab_switch_detection = settings.tab_switch_detection
    ps.min_face_confidence = settings.min_face_confidence
    ps.max_head_rotation = settings.max_head_rotation
    ps.detection_interval = settings.detection_interval
    ps.initial_health = settings.initial_health
    ps.health_warning_threshold = settings.health_warning_threshold
    ps.auto_submit_on_zero_health = settings.auto_submit_on_zero_health

    db.commit()

    return {"message": "Proctoring settings updated successfully", "settings": settings}


@router.get("/exam/{exam_id}/proctoring-settings", response_model=ExamProctoringConfig)
async def get_proctoring_settings(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await run_db(db, _get_proctoring_settings_blocking, exam_id, db, current_user)


def _get_proctoring_settings_blocking(
    exam_id: UUID,
    db: Session,
    current_user: User
):
    """Get proctoring settings for an exam"""
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found")

    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == exam_id
    ).first()

    if ps is None:
        return ExamProctoringConfig()

    return ExamProctoringConfig(
        camera_enabled=ps.camera_enabled,
        microphone_enabled=ps.microphone_enabled,
        face_detection_enabled=ps.face_detection_enabled,
        multiple_face_detection=ps.multiple_face_detection,
        head_pose_detection=ps.head_pose_detection,
        tab_switch_detection=ps.tab_switch_detection,
        min_face_confidence=float(ps.min_face_confidence),
        max_head_rotation=float(ps.max_head_rotation),
        detection_interval=ps.detection_interval,
        initial_health=ps.initial_health,
        health_warning_threshold=ps.health_warning_threshold,
        auto_submit_on_zero_health=ps.auto_submit_on_zero_health,
    )


@router.post("/violation")
async def report_violation(
    event: ProctoringEvent,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await run_db(db, _report_violation_blocking, event, db, current_user)


def _report_violation_blocking(
    event: ProctoringEvent,
    db: Session,
    current_user: User
):
    """
    Report a client-detected proctoring violation (tab switch, fullscreen
    exit, copy/paste, etc.) and update health.

    Server-side frame/audio analysis is persisted by the /monitor/frame and
    /monitor/audio endpoints directly, so the frontend must NOT re-report those
    flags here — doing so used to double-log every camera violation. Health is
    applied incrementally to the persisted column via the shared writer rather
    than replaying the whole cheat log on every request.
    """
    attempt = db.query(ExamAttempt).filter(
        ExamAttempt.id == event.attempt_id,
        ExamAttempt.student_id == current_user.id
    ).first()

    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam attempt not found")

    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == attempt.exam_id
    ).first()

    # Persists logs, applies the penalty atomically, and publishes the new
    # health to every API process (Redis pub/sub) — including the one holding
    # this student's WebSocket, which may not be this one.
    record = health_mod.record_violations(
        db, attempt, event.flags, ps=ps, event_type=event.event_type
    )
    health_status = record["health"]

    return {
        "health": health_status,
        "violations_logged": record["logged"],
        "auto_submitted": record["auto_submitted"]
    }


@router.get("/attempt/{attempt_id}/health")
async def get_attempt_health(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Students poll this as a backstop to the WebSocket. Served from the Redis
    health snapshot (owner-checked) with zero DB work; falls back to Postgres
    on a miss, for examiners, or when Redis is down.
    """
    raw = await cache.get(events.snapshot_key(str(attempt_id)))
    if raw and raw.get("owner") == str(current_user.id):
        return raw["data"]
    health = await run_db(db, _get_attempt_health_blocking, attempt_id, db, current_user)
    if current_user.role == "student" and cache.raw_client is not None:
        try:   # fill-on-miss must never overwrite a newer published snapshot: NX
            await cache.raw_client.set(
                events.snapshot_key(str(attempt_id)),
                events._snapshot_payload(current_user.id, health),
                ex=events.SNAPSHOT_TTL_SECONDS, nx=True,
            )
        except Exception:
            pass
    return health


def _get_attempt_health_blocking(
    attempt_id: UUID,
    db: Session,
    current_user: User
):
    """Get current health status for an attempt"""
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()

    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    if current_user.role == 'student' and str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == attempt.exam_id
    ).first()

    # Reads the persisted health column (lazy-inits older NULL rows) instead of
    # replaying the whole cheat log on every poll.
    return health_mod.current_health_status(db, attempt, ps=ps)


@router.get("/attempt/{attempt_id}/violations")
def get_attempt_violations(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get all violations for an attempt"""
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()

    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()

    if current_user.role == 'student':
        if str(attempt.student_id) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    elif current_user.role == 'examiner':
        if str(exam.created_by) != str(current_user.id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    violations = db.query(CheatLog).filter(
        CheatLog.attempt_id == attempt_id
    ).order_by(CheatLog.timestamp.desc()).all()

    violations_by_type = defaultdict(list)
    for v in violations:
        violations_by_type[v.flag_type].append({
            'id': str(v.id),
            'severity': scoring.normalize_severity(v.severity),
            'timestamp': v.timestamp.isoformat(),
            'metadata': v.meta_data  # column is meta_data (not metadata)
        })

    return {
        'total_violations': len(violations),
        'by_type': dict(violations_by_type),
        'timeline': [
            {
                'id': str(v.id),
                'type': v.flag_type,
                'severity': scoring.normalize_severity(v.severity),
                'timestamp': v.timestamp.isoformat(),
                'metadata': v.meta_data  # column is meta_data (not metadata)
            }
            for v in violations
        ]
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────

def _authorize_ws_attempt(token: Optional[str], attempt_id: str):
    """
    Validate the JWT (passed as a query param, since browsers can't set headers
    on a WebSocket) and confirm the caller may watch this attempt.

    Returns the ExamAttempt on success, or None if auth/authorization fails.
    Runs in its own DB session and detaches the attempt before returning.
    """
    if not token:
        return None
    payload = decode_access_token(token)
    if not payload:
        return None
    email = payload.get("sub")
    if not email:
        return None

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        if not user or (payload.get("tv", 0) or 0) != (user.token_version or 0):
            return None
        attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
        if not attempt:
            return None

        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        if role == "student":
            if str(attempt.student_id) != str(user.id):
                return None
        elif role == "examiner":
            exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
            if not exam or str(exam.created_by) != str(user.id):
                return None
        elif role != "admin":
            return None

        db.expunge(attempt)
        return attempt
    finally:
        db.close()


@router.websocket("/ws/proctoring/{attempt_id}")
async def proctoring_websocket(
    websocket: WebSocket,
    attempt_id: str,
    token: Optional[str] = Query(None),
):
    """
    WebSocket endpoint for real-time proctoring updates.

    Authenticated via a ``?token=<jwt>`` query param and authorized to the
    attempt's owner (student), the exam's examiner, or an admin. Previously this
    endpoint accepted ANY connection for ANY attempt id with no auth at all.
    """
    # Auth + the initial snapshot use the sync ORM, so they run in the
    # threadpool; the event loop only ever awaits socket I/O.
    attempt = await run_in_threadpool(_authorize_ws_attempt, token, attempt_id)
    if attempt is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(attempt_id, websocket)

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Proctoring monitoring active",
            "attempt_id": attempt_id
        })

        # Snapshot on (re)connect: pub/sub is at-most-once, so anything missed
        # while disconnected is healed by sending the persisted value now.
        snapshot = await run_in_threadpool(_health_snapshot, attempt_id)
        if snapshot is not None:
            await websocket.send_json({"type": "health_update", "data": snapshot})

        while True:
            data = await websocket.receive_json()

            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})

    except WebSocketDisconnect:
        manager.disconnect(attempt_id, websocket)
    except Exception as e:
        logger.warning("WebSocket error for attempt %s: %s", attempt_id, e)
        manager.disconnect(attempt_id, websocket)


def _health_snapshot(attempt_id: str) -> Optional[dict]:
    db = SessionLocal()
    try:
        attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
        if not attempt:
            return None
        ps = db.query(ProctoringSettingsModel).filter(
            ProctoringSettingsModel.exam_id == attempt.exam_id
        ).first()
        return health_mod.current_health_status(db, attempt, ps=ps)
    finally:
        db.close()


# ── Health Recovery Endpoint ───────────────────────────────────────────────────

class RecoverRequest(BaseModel):
    attempt_id: UUID
    # Kept for API compatibility; the server decides the real amount.
    amount: int = Field(3, ge=1, le=20)


# Recovery policy — enforced HERE, not trusted from the client. Previously any
# client could call /recover in a loop and hold itself at full health.
RECOVERY_CLEAN_SECONDS = 60     # must have no violation for this long
RECOVERY_INTERVAL_SECONDS = 60  # at most one recovery per interval per attempt
RECOVERY_MAX_AMOUNT = 3


@router.post("/recover")
async def recover_health(
    req: RecoverRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return await run_db(db, _recover_health_blocking, req, db, current_user)


def _recover_health_blocking(
    req: RecoverRequest,
    db: Session,
    current_user: User
):
    """
    Restore a small amount of health after a clean period. The frontend may
    call this whenever it likes; the server only grants recovery when the
    attempt really has been violation-free for RECOVERY_CLEAN_SECONDS and no
    recovery was granted in the last RECOVERY_INTERVAL_SECONDS (a distributed
    limiter, so hopping between API replicas doesn't help either).
    """
    attempt = db.query(ExamAttempt).filter(
        ExamAttempt.id == req.attempt_id,
        ExamAttempt.student_id == current_user.id
    ).first()

    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attempt not found")

    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == attempt.exam_id
    ).first()

    since = health_mod.seconds_since_last_violation(db, attempt.id)
    clean = since is None or since >= RECOVERY_CLEAN_SECONDS
    if not clean or not rate_limit.allow_sync(
        f"recover:{attempt.id}", 1, RECOVERY_INTERVAL_SECONDS
    ):
        return {
            "recovered": 0,
            "eligible": False,
            "health": health_mod.current_health_status(db, attempt, ps=ps),
        }

    record = health_mod.recover(db, attempt, min(req.amount, RECOVERY_MAX_AMOUNT), ps=ps)
    return {"recovered": record["recovered"], "eligible": True, "health": record["health"]}


# ── Suspicion Score ───────────────────────────────────────────────────

@router.get("/attempt/{attempt_id}/suspicion-score")
def get_suspicion_score(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Compute a 0-100 suspicion score for an attempt.
    Factors: violation frequency, severity weighting, timing clustering.
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if current_user.role == 'student' and str(attempt.student_id) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")
    if current_user.role == 'examiner' and str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    violations = db.query(CheatLog).filter(CheatLog.attempt_id == attempt_id).all()

    if not violations:
        return {"score": 0, "label": "Clean", "breakdown": {}}

    # Weights + severity now come from the shared scoring module. The old inline
    # tables parsed severity as the enum NAME ('HIGH'), which never matched the
    # lowercase keys — so the severity term was silently always the minimum.
    raw_weight = scoring.total_suspicion_weight(
        (v.flag_type, v.severity) for v in violations
    )
    freq_score = min(60, raw_weight * 0.8)

    if len(violations) >= 2:
        sorted_v = sorted(violations, key=lambda v: v.timestamp)
        gaps = [
            (sorted_v[i+1].timestamp - sorted_v[i].timestamp).total_seconds()
            for i in range(len(sorted_v) - 1)
        ]
        tight = sum(1 for g in gaps if g < 30)
        cluster_score = min(25, tight * 5)
    else:
        cluster_score = 0

    high_count = sum(1 for v in violations if scoring.normalize_severity(v.severity) == "high")
    ratio = high_count / len(violations)
    severity_score = min(15, ratio * 20)

    total = min(100, int(freq_score + cluster_score + severity_score))

    if total < 15:
        label = "Clean"
    elif total < 35:
        label = "Low suspicion"
    elif total < 60:
        label = "Moderate suspicion"
    elif total < 80:
        label = "High suspicion"
    else:
        label = "Very high suspicion"

    return {
        "score": total,
        "label": label,
        "total_violations": len(violations),
        "breakdown": {
            "frequency_score": round(freq_score, 1),
            "clustering_score": round(cluster_score, 1),
            "severity_score": round(severity_score, 1),
        }
    }


# ── Live Proctoring Feed (examiner view) ───────────────────────────────

@router.get("/exam/{exam_id}/live-feed")
def get_live_feed(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Returns real-time summary of all active attempts for an exam.
    Shows student name, health %, violation count, last flag.
    """
    if current_user.role not in ['examiner', 'admin']:
        raise HTTPException(status_code=403, detail="Examiners only")

    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if current_user.role == 'examiner' and str(exam.created_by) != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied")

    from app.models.user import User as UserModel

    # Query 1: active attempts + student identity in one JOIN.
    rows = (
        db.query(ExamAttempt, UserModel.full_name, UserModel.email)
        .join(UserModel, UserModel.id == ExamAttempt.student_id)
        .filter(
            ExamAttempt.exam_id == exam_id,
            ExamAttempt.status == AttemptStatus.IN_PROGRESS,
        )
        .all()
    )
    ids = [a.id for a, _, _ in rows]

    # Query 2: violation counts per attempt (GROUP BY, not N COUNT queries).
    counts = dict(
        db.query(CheatLog.attempt_id, func.count(CheatLog.id))
        .filter(CheatLog.attempt_id.in_(ids))
        .group_by(CheatLog.attempt_id)
        .all()
    ) if ids else {}

    # Query 3: latest flag per attempt with DISTINCT ON, served by the
    # (attempt_id, timestamp DESC) index.
    latest = {
        log.attempt_id: log
        for log in (
            db.query(CheatLog)
            .filter(CheatLog.attempt_id.in_(ids))
            .distinct(CheatLog.attempt_id)
            .order_by(CheatLog.attempt_id, CheatLog.timestamp.desc())
            .all()
        )
    } if ids else {}

    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == exam_id
    ).first()
    maximum = health_mod.initial_health(ps)

    feed = []
    for attempt, full_name, email in rows:
        n = counts.get(attempt.id, 0)
        current = attempt.current_health if attempt.current_health is not None else maximum
        log = latest.get(attempt.id)
        last_flag = None
        if log is not None:
            last_flag = {
                "type": log.flag_type,
                "severity": scoring.normalize_severity(log.severity),
                "timestamp": log.timestamp.isoformat(),
            }
        health = health_mod.health_status(current, maximum, n)
        feed.append({
            "attempt_id": str(attempt.id),
            "student_name": full_name or "Unknown",
            "student_email": email or "",
            "health_percentage": health["percentage"],
            "health_status": health["status"],
            "violation_count": n,
            "last_flag": last_flag,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
            "deadline": attempt.deadline.isoformat() if attempt.deadline else None,
        })

    feed.sort(key=lambda x: x["violation_count"], reverse=True)

    return {
        "exam_id": str(exam_id),
        "active_count": len(feed),
        "flagged_count": sum(1 for s in feed if s["violation_count"] > 0),
        "students": feed
    }
