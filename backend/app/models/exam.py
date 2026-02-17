from sqlalchemy import Column, String, Integer, Numeric, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base

#  REMOVED: `from app.models.exam import Exam` was here causing circular import


class ExamStatus(str, enum.Enum):
    DRAFT = "draft"
    LIVE = "live"
    ENDED = "ended"


class Exam(Base):
    __tablename__ = "exams"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    description = Column(String, nullable=True)
    duration_minutes = Column(Integer, nullable=False)
    total_marks = Column(Integer, nullable=False)
    pass_percentage = Column(Numeric(5, 2), default=40.00)
    status = Column(Enum(ExamStatus), nullable=False, default=ExamStatus.DRAFT)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    questions = relationship("Question", back_populates="exam", cascade="all, delete-orphan")
    attempts = relationship("ExamAttempt", back_populates="exam")
    proctoring_settings = relationship("ProctoringSettings", back_populates="exam", uselist=False)