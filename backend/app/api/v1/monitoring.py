from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from uuid import UUID
from app.core.database import get_db
from app.models.user import User
from app.models.attempt import ExamAttempt
from app.models.cheat_log import CheatLog
from app.api.deps import get_current_user, require_role
from app.ai_monitor.face_detector import FaceDetector
from app.ai_monitor.audio_analyzer import AudioAnalyzer

router = APIRouter()

face_detector = FaceDetector()
audio_analyzer = AudioAnalyzer()

@router.post("/frame")
async def analyze_frame(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Analyze webcam frame for cheating detection
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found"
        )
    
    if attempt.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    # Read image bytes
    image_bytes = await file.read()
    
    # Analyze frame
    result = face_detector.analyze_frame(image_bytes)
    
    # Log flags if any
    if result['flags']:
        for flag in result['flags']:
            log = CheatLog(
                attempt_id=attempt_id,
                flag_type=flag,
                severity=result['severity'],
                meta_data={'num_faces': result.get('num_faces', 0)}
            )
            db.add(log)
        
        # Increment cheating flags count
        attempt.cheating_flags += len(result['flags'])
        
        db.commit()
    
    return result

@router.post("/audio")
async def analyze_audio(
    attempt_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(["student"]))
):
    """
    Analyze audio for cheating detection
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found"
        )
    
    if attempt.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    # Read audio bytes
    audio_bytes = await file.read()
    
    # Analyze audio
    result = audio_analyzer.analyze_audio(audio_bytes)
    
    # Log flags if any
    if result['flags']:
        for flag in result['flags']:
            log = CheatLog(
                attempt_id=attempt_id,
                flag_type=flag,
                severity=result['severity'],
                meta_data={'rms_energy': result.get('rms_energy', 0)}
            )
            db.add(log)
        
        # Increment cheating flags count
        attempt.cheating_flags += len(result['flags'])
        
        db.commit()
    
    return result

@router.get("/flags/{attempt_id}", response_model=list)
def get_cheat_flags(
    attempt_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all cheat flags for an attempt
    """
    attempt = db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
    
    if not attempt:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attempt not found"
        )
    
    # Check permissions
    if current_user.role == "student" and attempt.student_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized"
        )
    
    logs = db.query(CheatLog).filter(CheatLog.attempt_id == attempt_id).all()
    
    return [
        {
            'id': str(log.id),
            'flag_type': log.flag_type,
            'severity': log.severity,
            'timestamp': log.timestamp.isoformat(),
            'metadata': log.meta_data  # Return as 'metadata' to frontend
        }
        for log in logs
    ]