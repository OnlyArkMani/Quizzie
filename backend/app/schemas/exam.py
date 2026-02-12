from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from uuid import UUID

class ExamBase(BaseModel):
    title: str
    description: Optional[str] = None
    duration_minutes: int
    total_marks: int
    pass_percentage: float = 40.0
    status: str = "draft"

class ExamCreate(ExamBase):
    pass

class ExamUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    total_marks: Optional[int] = None
    pass_percentage: Optional[float] = None
    status: Optional[str] = None

class Exam(ExamBase):
    id: UUID
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ExamWithQuestions(Exam):
    questions: List["Question"] = []