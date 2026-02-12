from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class ResponseCreate(BaseModel):
    question_id: UUID
    selected_option_ids: List[UUID]
    marked_for_review: bool = False

class ResponseUpdate(BaseModel):
    selected_option_ids: Optional[List[UUID]] = None
    marked_for_review: Optional[bool] = None

class Response(BaseModel):
    id: UUID
    attempt_id: UUID
    question_id: UUID
    selected_option_ids: List[UUID]
    is_correct: Optional[bool] = None
    marks_awarded: Optional[float] = None
    marked_for_review: bool
    answered_at: datetime
    
    class Config:
        from_attributes = True

class AttemptCreate(BaseModel):
    exam_id: UUID

class AttemptSubmit(BaseModel):
    responses: List[ResponseCreate]

class Attempt(BaseModel):
    id: UUID
    exam_id: UUID
    student_id: UUID
    started_at: datetime
    submitted_at: Optional[datetime] = None
    time_taken_seconds: Optional[int] = None
    score: Optional[float] = None
    status: str
    cheating_flags: int
    
    class Config:
        from_attributes = True