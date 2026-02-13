from sqlalchemy import Column, String, DateTime, ForeignKey, Enum, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base

class CheatSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class CheatLog(Base):
    __tablename__ = "cheat_logs"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"))
    flag_type = Column(String(50), nullable=False)
    severity = Column(Enum(CheatSeverity), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    # CHANGED: metadata -> meta_data (to avoid SQLAlchemy reserved word)
    meta_data = Column(JSON, nullable=True)
    
    # Relationships
    attempt = relationship("ExamAttempt", back_populates="cheat_logs")