from sqlalchemy import Column, String, Integer, Numeric, DateTime, ForeignKey, Enum, Boolean, ARRAY
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from datetime import datetime
import uuid
import enum
from app.core.database import Base

class AttemptStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    SUBMITTED = "submitted"
    EVALUATED = "evaluated"

class ExamAttempt(Base):
    __tablename__ = "exam_attempts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id"))
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    started_at = Column(DateTime, default=datetime.utcnow)
    submitted_at = Column(DateTime, nullable=True)
    time_taken_seconds = Column(Integer, nullable=True)
    score = Column(Numeric(5, 2), nullable=True)
    status = Column(Enum(AttemptStatus), nullable=False, default=AttemptStatus.IN_PROGRESS)
    cheating_flags = Column(Integer, default=0)
    
    # Relationships
    exam = relationship("Exam", back_populates="attempts")
    responses = relationship("Response", back_populates="attempt", cascade="all, delete-orphan")
    cheat_logs = relationship("CheatLog", back_populates="attempt", cascade="all, delete-orphan")

class Response(Base):
    __tablename__ = "responses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"))
    selected_option_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False)
    is_correct = Column(Boolean, nullable=True)
    marks_awarded = Column(Numeric(5, 2), nullable=True)
    marked_for_review = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    attempt = relationship("ExamAttempt", back_populates="responses")