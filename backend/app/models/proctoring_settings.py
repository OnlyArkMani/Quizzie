from sqlalchemy import Column, ForeignKey, Integer, Numeric, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from app.core.database import Base

class ProctoringSettings(Base):
    __tablename__ = "proctoring_settings"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"), nullable=False)
    
    camera_enabled = Column(Boolean, nullable=False, default=True)
    microphone_enabled = Column(Boolean, nullable=False, default=False)
    face_detection_enabled = Column(Boolean, nullable=False, default=True)
    multiple_face_detection = Column(Boolean, nullable=False, default=True)
    head_pose_detection = Column(Boolean, nullable=False, default=True)
    tab_switch_detection = Column(Boolean, nullable=False, default=True)
    
    min_face_confidence = Column(Numeric(3, 2), nullable=False, default=0.6)
    max_head_rotation = Column(Numeric(5, 2), nullable=False, default=30.0)
    detection_interval = Column(Integer, nullable=False, default=2)
    initial_health = Column(Integer, nullable=False, default=100)
    health_warning_threshold = Column(Integer, nullable=False, default=40)
    auto_submit_on_zero_health = Column(Boolean, nullable=False, default=True)
    
    # Relationship
    exam = relationship("Exam", back_populates="proctoring_settings")