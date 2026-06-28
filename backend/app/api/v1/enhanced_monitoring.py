"""
Enhanced Proctoring API Endpoints
Handles real-time monitoring, health tracking, and configuration
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from uuid import UUID
import asyncio
import logging
from collections import defaultdict

from app.core.database import get_db, SessionLocal
from app.api.deps import get_current_user
from app.core.security import decode_access_token
from app.models.user import User
from app.models.attempt import ExamAttempt, AttemptStatus
from app.models.cheat_log import CheatLog, CheatSeverity
from app.models.exam import Exam
# Import with alias to avoid name conflict with the Pydantic schema below
from app.models.proctoring_settings import ProctoringSettings as ProctoringSettingsModel
from app.ai_monitor import scoring, health as health_mod

logger = logging.getLogger(__name__)

router = APIRouter()


# WebSocket connection manager for real-time updates
class ConnectionManager:
    """Manages WebSocket connections for real-time proctoring"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.attempt_health: Dict[str, int] = {}

    async def connect(self, attempt_id: str, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[attempt_id] = websocket
        self.attempt_health[attempt_id] = 100  # Initial health

    def disconnect(self, attempt_id: str):
        if attempt_id in self.active_connections:
            del self.active_connections[attempt_id]
        if attempt_id in self.attempt_health:
            del self.attempt_health[attempt_id]

    async def send_health_update(self, attempt_id: str, health_data: dict):
        if attempt_id in self.active_connections:
            try:
                await self.active_connections[attempt_id].send_json({
                    "type": "health_update",
                    "data": health_data
                })
            except Exception:
                self.disconnect(attempt_id)

    async def send_violation_alert(self, attempt_id: str, violation: dict):
        if attempt_id in self.active_connections:
            try:
                await self.active_connections[attempt_id].send_json({
                    "type": "violation_alert",
                    "data": violation
                })
            except Exception:
                self.disconnect(attempt_id)


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
async def update_proctoring_settings(
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
    warning_threshold = ps.health_warning_threshold if ps else 40

    record = health_mod.record_violations(
        db, attempt, event.flags, ps=ps, event_type=event.event_type
    )
    health_status = record["health"]

    await manager.send_health_update(str(event.attempt_id), health_status)

    if health_status['percentage'] <= warning_threshold:
        await manager.send_violation_alert(str(event.attempt_id), {
            'message': f"⚠️ Health is at {health_status['percentage']:.0f}%",
            'severity': 'high',
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

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
async def get_attempt_violations(
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
        if not user:
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
    attempt = _authorize_ws_attempt(token, attempt_id)
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

        # Send the persisted health immediately (no full-log replay).
        db = SessionLocal()
        try:
            attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
            if attempt:
                ps = db.query(ProctoringSettingsModel).filter(
                    ProctoringSettingsModel.exam_id == attempt.exam_id
                ).first()
                await websocket.send_json({
                    "type": "health_update",
                    "data": health_mod.current_health_status(db, attempt, ps=ps)
                })
        finally:
            db.close()

        while True:
            data = await websocket.receive_json()

            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})

    except WebSocketDisconnect:
        manager.disconnect(attempt_id)
    except Exception as e:
        logger.warning("WebSocket error for attempt %s: %s", attempt_id, e)
        manager.disconnect(attempt_id)


# ── Health Recovery Endpoint ───────────────────────────────────────────────────

class RecoverRequest(BaseModel):
    attempt_id: UUID
    amount: int = Field(3, ge=1, le=20)


@router.post("/recover")
async def recover_health(
    req: RecoverRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Restore a small amount of health for clean behaviour.
    Called by the frontend after 60 s with no violations.
    Only recovers up to the initial max — cannot overheal.

    Now persists to the health column. Previously this recomputed health from
    the log, added the amount, and returned it WITHOUT saving — so the recovered
    HP vanished on the next request, making the whole feature a no-op.
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

    record = health_mod.recover(db, attempt, req.amount, ps=ps)

    # Push updated health to WebSocket if connected
    await manager.send_health_update(str(req.attempt_id), record["health"])

    return {
        "recovered": record["recovered"],
        "health": record["health"]
    }


# ── Suspicion Score ───────────────────────────────────────────────────

@router.get("/attempt/{attempt_id}/suspicion-score")
async def get_suspicion_score(
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
async def get_live_feed(
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
    active_attempts = db.query(ExamAttempt).filter(
        ExamAttempt.exam_id == exam_id,
        ExamAttempt.submitted_at == None  # noqa: E711 — still in progress
    ).all()

    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == exam_id
    ).first()
    maximum = health_mod.initial_health(ps)

    feed = []
    dirty = False
    for attempt in active_attempts:
        student = db.query(UserModel).filter(UserModel.id == attempt.student_id).first()
        violations = db.query(CheatLog).filter(CheatLog.attempt_id == attempt.id).all()

        # Read the persisted health column (lazy-init older NULL rows) instead
        # of replaying every student's full cheat log on each poll.
        current = health_mod.ensure_health(attempt, ps)
        if db.is_modified(attempt):
            dirty = True

        last_flag = None
        if violations:
            latest = max(violations, key=lambda v: v.timestamp)
            last_flag = {
                "type": latest.flag_type,
                "severity": scoring.normalize_severity(latest.severity),
                "timestamp": latest.timestamp.isoformat()
            }

        health = health_mod.health_status(current, maximum, len(violations))
        feed.append({
            "attempt_id": str(attempt.id),
            "student_name": student.full_name if student else "Unknown",
            "student_email": student.email if student else "",
            "health_percentage": health["percentage"],
            "health_status": health["status"],
            "violation_count": len(violations),
            "last_flag": last_flag,
            "started_at": attempt.started_at.isoformat() if attempt.started_at else None,
        })

    if dirty:
        db.commit()

    feed.sort(key=lambda x: x["violation_count"], reverse=True)

    return {
        "exam_id": str(exam_id),
        "active_count": len(feed),
        "flagged_count": sum(1 for s in feed if s["violation_count"] > 0),
        "students": feed
    }
