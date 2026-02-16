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
            except:
                self.disconnect(attempt_id)
    
    async def send_violation_alert(self, attempt_id: str, violation: dict):
        if attempt_id in self.active_connections:
            try:
                await self.active_connections[attempt_id].send_json({
                    "type": "violation_alert",
                    "data": violation
                })
            except:
                self.disconnect(attempt_id)

manager = ConnectionManager()


# Pydantic schemas
class ProctoringSettings(BaseModel):
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


class ExamWithProctoring(BaseModel):
    """Exam model with proctoring settings"""
    id: UUID
    title: str
    proctoring_settings: ProctoringSettings
    
    class Config:
        from_attributes = True


# API Endpoints

@router.post("/exam/{exam_id}/proctoring-settings")
async def update_proctoring_settings(
    exam_id: UUID,
    settings: ProctoringSettings,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update proctoring settings for an exam (Examiner only)
    """
    # Check if user is examiner/admin
    if current_user.role not in ['examiner', 'admin']:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only examiners can update proctoring settings"
        )
    
    # Get exam
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found"
        )
    
    # Check ownership
    if exam.created_by != current_user.id and current_user.role != 'admin':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to modify this exam"
        )
    
    # Store settings in exam metadata (you may need to add a JSONB column to exams table)
    # For now, we'll store it in a separate table or use exam description temporarily
    # In production, add: proctoring_settings = Column(JSONB, nullable=True) to Exam model
    
    # This is a simplified version - you should add proctoring_settings column to Exam model
    exam.description = json.dumps(settings.dict()) if not exam.description else exam.description
    
    db.commit()
    
    return {
        "message": "Proctoring settings updated successfully",
        "settings": settings
    }


@router.get("/exam/{exam_id}/proctoring-settings", response_model=ProctoringSettings)
async def get_proctoring_settings(
    exam_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get proctoring settings for an exam
    """
    exam = db.query(Exam).filter(Exam.id == exam_id).first()
    if not exam:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found"
        )
    
    # Return default settings for now
    # In production, retrieve from exam.proctoring_settings column
    return ProctoringSettings()


@router.post("/violation")
async def report_violation(
    event: ProctoringEvent,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Report a proctoring violation and update health
    """
    # Verify attempt exists and belongs to current user
    attempt = db.query(ExamAttempt).filter(
        ExamAttempt.id == event.attempt_id,
        ExamAttempt.student_id == current_user.id
    ).first()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam attempt not found"
        )
    
    # Get exam and proctoring settings
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    settings = ProctoringSettings()  # Load from exam in production
    
    # Calculate health penalties
    health_calculator = HealthCalculator(settings.initial_health)
    
    # Get current health from attempt metadata (or separate table)
    current_health = getattr(attempt, 'current_health', settings.initial_health)
    health_calculator.current_health = current_health
    
    violation_logs = []
    health_updates = []
    
    # Process each flag
    for flag in event.flags:
        # Apply health penalty
        new_health = health_calculator.apply_violation(
            flag['type'],
            flag.get('severity', 'medium')
        )
        
        # Create cheat log
        cheat_log = CheatLog(
            attempt_id=attempt.id,
            flag_type=flag['type'],
            severity=flag.get('severity', 'medium'),
            timestamp=event.timestamp,
            metadata={
                'message': flag.get('message'),
                'event_type': event.event_type,
                **flag.get('metadata', {})
            }
        )
        db.add(cheat_log)
        violation_logs.append(cheat_log)
        
        # Increment cheating flags counter
        attempt.cheating_flags += 1
    
    # Update attempt health (you may need to add current_health column)
    # attempt.current_health = health_calculator.current_health
    
    # Check if health is zero and auto-submit is enabled
    if health_calculator.current_health <= 0 and settings.auto_submit_on_zero_health:
        attempt.status = 'submitted'
        attempt.submitted_at = datetime.utcnow()
    
    db.commit()
    
    # Send real-time update via WebSocket
    health_status = health_calculator.get_health_status()
    await manager.send_health_update(str(event.attempt_id), health_status)
    
    # Send violation alert
    if health_status['percentage'] <= settings.health_warning_threshold:
        await manager.send_violation_alert(str(event.attempt_id), {
            'message': f"⚠️ Health is at {health_status['percentage']:.0f}%",
            'severity': 'high'
        })
    
    return {
        "health": health_status,
        "violations_logged": len(violation_logs),
        "auto_submitted": health_calculator.current_health <= 0 and settings.auto_submit_on_zero_health
    }


@router.get("/attempt/{attempt_id}/health")
async def get_attempt_health(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get current health status for an attempt
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found"
        )
    
    # Check permissions
    if current_user.role == 'student' and attempt.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    # Get violation count and calculate health
    violations = db.query(CheatLog).filter(CheatLog.attempt_id == attempt_id).all()
    
    # Reconstruct health from violations
    health_calculator = HealthCalculator(initial_health=100)
    
    for violation in violations:
        health_calculator.apply_violation(
            violation.flag_type,
            violation.severity
        )
    
    return health_calculator.get_health_status()


@router.get("/attempt/{attempt_id}/violations")
async def get_attempt_violations(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all violations for an attempt (Examiner view)
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found"
        )
    
    # Check permissions
    exam = db.query(Exam).filter(Exam.id == attempt.exam_id).first()
    if current_user.role == 'student':
        if attempt.student_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    elif current_user.role == 'examiner':
        if exam.created_by != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
    
    violations = db.query(CheatLog).filter(
        CheatLog.attempt_id == attempt_id
    ).order_by(CheatLog.timestamp.desc()).all()
    
    # Group by type
    violations_by_type = defaultdict(list)
    for v in violations:
        violations_by_type[v.flag_type].append({
            'id': str(v.id),
            'severity': v.severity,
            'timestamp': v.timestamp.isoformat(),
            'metadata': v.metadata
        })
    
    return {
        'total_violations': len(violations),
        'by_type': dict(violations_by_type),
        'timeline': [
            {
                'id': str(v.id),
                'type': v.flag_type,
                'severity': v.severity,
                'timestamp': v.timestamp.isoformat(),
                'metadata': v.metadata
            }
            for v in violations
        ]
    }


# WebSocket endpoint for real-time monitoring
@router.websocket("/ws/proctoring/{attempt_id}")
async def proctoring_websocket(
    websocket: WebSocket,
    attempt_id: str,
    db: Session = Depends(get_db)
):
    """
    WebSocket endpoint for real-time proctoring updates
    """
    await manager.connect(attempt_id, websocket)
    
    try:
        # Send initial health status
        await websocket.send_json({
            "type": "connected",
            "message": "Proctoring monitoring active",
            "attempt_id": attempt_id
        })
        
        while True:
            # Receive messages from client
            data = await websocket.receive_json()
            
            # Handle different message types
            if data.get('type') == 'ping':
                await websocket.send_json({'type': 'pong'})
            
            elif data.get('type') == 'frame_data':
                # Process frame data (you can add ML analysis here)
                pass
            
    except WebSocketDisconnect:
        manager.disconnect(attempt_id)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(attempt_id)


# Helper class (same as in face detector)
class HealthCalculator:
    """Calculate health decrease based on violations"""
    
    PENALTIES = {
        'no_face': 10,
        'multiple_faces': 15,
        'looking_away': 5,
        'face_tracking_lost': 5,
        'tab_switch': 8,
        'suspicious_audio': 3,
        'excessive_movement': 2
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
            'timestamp': datetime.utcnow()
        })
        
        return self.current_health
    
    def get_health_status(self) -> Dict[str, any]:
        health_percentage = (self.current_health / self.initial_health) * 100
        
        if health_percentage > 70:
            status = 'good'
        elif health_percentage > 40:
            status = 'warning'
        elif health_percentage > 0:
            status = 'critical'
        else:
            status = 'failed'
        
        return {
            'current': self.current_health,
            'max': self.initial_health,
            'percentage': health_percentage,
            'status': status,
            'violations_count': len(self.violation_history)
        }