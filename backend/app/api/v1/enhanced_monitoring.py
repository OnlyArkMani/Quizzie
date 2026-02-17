"""
Enhanced Proctoring API Endpoints
Handles real-time monitoring, health tracking, and configuration
"""
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from sqlalchemy.orm import Session
from typing import List, Optional, Dict
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID
import json
import asyncio
from collections import defaultdict

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.attempt import ExamAttempt
from app.models.cheat_log import CheatLog
from app.models.exam import Exam
# FIX Bug 2: Import with alias to avoid name conflict with Pydantic schema below
from app.models.proctoring_settings import ProctoringSettings as ProctoringSettingsModel

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

# FIX Bug 2: Renamed from ProctoringSettings → ExamProctoringConfig to avoid
#            conflict with the SQLAlchemy model imported above.
class ExamProctoringConfig(BaseModel):
    """Proctoring configuration settings for an exam"""
    camera_enabled: bool = True
    microphone_enabled: bool = False
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
    # FIX Bug 2: Use renamed Pydantic schema
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
        # Return defaults if no custom settings stored yet
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
    """Report a proctoring violation and update health"""
    attempt = db.query(ExamAttempt).filter(
        ExamAttempt.id == event.attempt_id,
        ExamAttempt.student_id == current_user.id
    ).first()

    if not attempt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Exam attempt not found")

    # Load proctoring settings
    ps = db.query(ProctoringSettingsModel).filter(
        ProctoringSettingsModel.exam_id == attempt.exam_id
    ).first()
    cfg = ExamProctoringConfig(
        initial_health=ps.initial_health if ps else 100,
        health_warning_threshold=ps.health_warning_threshold if ps else 40,
        auto_submit_on_zero_health=ps.auto_submit_on_zero_health if ps else True,
    )

    health_calculator = HealthCalculator(cfg.initial_health)

    # Reconstruct current health from existing violations
    existing = db.query(CheatLog).filter(CheatLog.attempt_id == event.attempt_id).all()
    for v in existing:
        health_calculator.apply_violation(v.flag_type, str(v.severity).replace('CheatSeverity.', ''))

    violation_logs = []

    for flag in event.flags:
        health_calculator.apply_violation(
            flag['type'],
            flag.get('severity', 'medium')
        )

        # FIX Bug 1: Use meta_data (not metadata)
        cheat_log = CheatLog(
            attempt_id=attempt.id,
            flag_type=flag['type'],
            severity=flag.get('severity', 'medium'),
            timestamp=event.timestamp,
            meta_data={
                'message': flag.get('message'),
                'event_type': event.event_type,
                **flag.get('metadata', {})
            }
        )
        db.add(cheat_log)
        violation_logs.append(cheat_log)
        attempt.cheating_flags = (attempt.cheating_flags or 0) + 1

    auto_submitted = False
    if health_calculator.current_health <= 0 and cfg.auto_submit_on_zero_health:
        attempt.status = 'submitted'
        attempt.submitted_at = datetime.utcnow()
        auto_submitted = True

    db.commit()

    health_status = health_calculator.get_health_status()
    await manager.send_health_update(str(event.attempt_id), health_status)

    if health_status['percentage'] <= cfg.health_warning_threshold:
        await manager.send_violation_alert(str(event.attempt_id), {
            'message': f"⚠️ Health is at {health_status['percentage']:.0f}%",
            'severity': 'high',
            'timestamp': datetime.utcnow().isoformat()
        })

    return {
        "health": health_status,
        "violations_logged": len(violation_logs),
        "auto_submitted": auto_submitted
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
    initial_health = ps.initial_health if ps else 100

    violations = db.query(CheatLog).filter(CheatLog.attempt_id == attempt_id).all()
    health_calculator = HealthCalculator(initial_health=initial_health)

    for v in violations:
        health_calculator.apply_violation(
            v.flag_type,
            str(v.severity).replace('CheatSeverity.', '')
        )

    return health_calculator.get_health_status()


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
            'severity': str(v.severity),
            'timestamp': v.timestamp.isoformat(),
            # FIX Bug 8: Use meta_data (not metadata)
            'metadata': v.meta_data
        })

    return {
        'total_violations': len(violations),
        'by_type': dict(violations_by_type),
        'timeline': [
            {
                'id': str(v.id),
                'type': v.flag_type,
                'severity': str(v.severity),
                'timestamp': v.timestamp.isoformat(),
                # FIX Bug 8: Use meta_data (not metadata)
                'metadata': v.meta_data
            }
            for v in violations
        ]
    }


# ─── WebSocket ────────────────────────────────────────────────────────────────

@router.websocket("/ws/proctoring/{attempt_id}")
async def proctoring_websocket(
    websocket: WebSocket,
    attempt_id: str,
    db: Session = Depends(get_db)
):
    """WebSocket endpoint for real-time proctoring updates"""
    await manager.connect(attempt_id, websocket)

    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Proctoring monitoring active",
            "attempt_id": attempt_id
        })

        while True:
            data = await websocket.receive_json()

            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})

    except WebSocketDisconnect:
        manager.disconnect(attempt_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(attempt_id)


# ─── Helper ───────────────────────────────────────────────────────────────────

class HealthCalculator:
    """Calculate health decrease based on violations"""

    PENALTIES = {
        'no_face': 10,
        'multiple_faces': 15,
        'looking_away': 5,
        'face_tracking_lost': 5,
        'tab_switch': 8,
        'suspicious_audio': 3,
        'excessive_movement': 2,
        'no_face_detected': 10,
        'multiple_faces_detected': 15,
    }

    def __init__(self, initial_health: int = 100):
        self.initial_health = initial_health
        self.current_health = initial_health
        self.violation_history = []

    def apply_violation(self, violation_type: str, severity: str = 'medium') -> int:
        base_penalty = self.PENALTIES.get(violation_type, 5)
        severity_multiplier = {'low': 0.5, 'medium': 1.0, 'high': 1.5}
        penalty = int(base_penalty * severity_multiplier.get(severity, 1.0))
        self.current_health = max(0, self.current_health - penalty)
        self.violation_history.append({
            'type': violation_type,
            'severity': severity,
            'penalty': penalty,
            'health_after': self.current_health,
        })
        return self.current_health

    def get_health_status(self) -> Dict:
        health_percentage = (self.current_health / self.initial_health) * 100 if self.initial_health > 0 else 0

        if health_percentage > 70:
            s = 'good'
        elif health_percentage > 40:
            s = 'warning'
        elif health_percentage > 0:
            s = 'critical'
        else:
            s = 'failed'

        return {
            'current': self.current_health,
            'max': self.initial_health,
            'percentage': health_percentage,
            'status': s,
            'violations_count': len(self.violation_history)
        }