from sqlalchemy import (
    Column, String, Integer, BigInteger, Numeric, DateTime, ForeignKey, Enum, Boolean,
    ARRAY, Index, UniqueConstraint, text,
)
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
    # Persisted proctoring health. NULL = not yet initialised (lazy init from
    # the exam's ProctoringSettings.initial_health on first violation/read).
    # Storing it avoids replaying the whole cheat_log history on every request
    # and lets health recovery actually persist.
    current_health = Column(Integer, nullable=True)

    # Server-authoritative end time: started_at + exam.duration_minutes, fixed at
    # start. Stored (not derived) so editing an exam's duration mid-exam cannot
    # move the goalposts for students who already started. NULL only for rows
    # created before migration 006 (treated as "no deadline").
    deadline = Column(DateTime, nullable=True)

    # Idempotency-Key of the request that submitted this attempt. A retried
    # submit carrying the same key gets the original result instead of an error.
    submit_idempotency_key = Column(String(64), nullable=True)

    __table_args__ = (
        # At most ONE in-progress attempt per (exam, student). A partial unique
        # index lets the database, not application code, win the race when two
        # /start requests arrive at the same instant. Submitted/evaluated
        # attempts are excluded so retakes stay possible.
        Index(
            "uq_one_active_attempt",
            "exam_id", "student_id",
            unique=True,
            postgresql_where=text("status = 'IN_PROGRESS'"),
        ),
    )

    # Relationships
    exam = relationship("Exam", back_populates="attempts")
    responses = relationship("Response", back_populates="attempt", cascade="all, delete-orphan")
    cheat_logs = relationship("CheatLog", back_populates="attempt", cascade="all, delete-orphan")

class Response(Base):
    __tablename__ = "responses"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    attempt_id = Column(UUID(as_uuid=True), ForeignKey("exam_attempts.id", ondelete="CASCADE"))
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id"))
    # MCQ selections. Nullable now that coding/subjective answers use answer_text.
    selected_option_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=True)
    # Free-text answer for coding/subjective questions (manually graded).
    answer_text = Column(String, nullable=True)
    is_correct = Column(Boolean, nullable=True)
    marks_awarded = Column(Numeric(5, 2), nullable=True)
    marked_for_review = Column(Boolean, default=False)
    answered_at = Column(DateTime, default=datetime.utcnow)
    # Client-side monotonic sequence number of the edit that produced this row.
    # Auto-saves can arrive out of order (retries, slow requests); the upsert
    # only overwrites when the incoming seq is newer, so a stale save can never
    # clobber a fresher answer.
    client_seq = Column(BigInteger, nullable=False, default=0, server_default="0")

    __table_args__ = (
        # One answer row per question per attempt — the key the auto-save
        # upsert (INSERT ... ON CONFLICT) targets. Also stops evaluation from
        # double-counting a question.
        UniqueConstraint("attempt_id", "question_id", name="uq_response_attempt_question"),
    )
    
    # Relationships
    attempt = relationship("ExamAttempt", back_populates="responses")