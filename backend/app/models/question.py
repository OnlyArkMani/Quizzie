from sqlalchemy import Column, String, Integer, Boolean, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
import enum
from app.core.database import Base

class QuestionType(str, enum.Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"

class Question(Base):
    __tablename__ = "questions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id = Column(UUID(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"))
    question_text = Column(String, nullable=False)
    question_type = Column(Enum(QuestionType), nullable=False)
    marks = Column(Integer, nullable=False, default=1)
    topic = Column(String(100), nullable=True)
    display_order = Column(Integer, nullable=False)
    
    # Relationships
    exam = relationship("Exam", back_populates="questions")
    options = relationship("Option", back_populates="question", cascade="all, delete-orphan")

class Option(Base):
    __tablename__ = "options"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_id = Column(UUID(as_uuid=True), ForeignKey("questions.id", ondelete="CASCADE"))
    option_text = Column(String, nullable=False)
    is_correct = Column(Boolean, nullable=False, default=False)
    display_order = Column(Integer, nullable=False)
    
    # Relationships
    question = relationship("Question", back_populates="options")