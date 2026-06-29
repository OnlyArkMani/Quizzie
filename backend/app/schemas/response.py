from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from uuid import UUID

class ResponseCreate(BaseModel):
    question_id: UUID
    # MCQ selections; empty for coding/subjective answers.
    selected_option_ids: List[UUID] = []
    # Free-text/code answer for coding/subjective questions.
    answer_text: Optional[str] = None
    marked_for_review: bool = False

class ResponseUpdate(BaseModel):
    selected_option_ids: Optional[List[UUID]] = None
    answer_text: Optional[str] = None
    marked_for_review: Optional[bool] = None

class Response(BaseModel):
    id: UUID
    attempt_id: UUID
    question_id: UUID
    selected_option_ids: Optional[List[UUID]] = []
    answer_text: Optional[str] = None
    is_correct: Optional[bool] = None
    marks_awarded: Optional[float] = None
    marked_for_review: bool
    answered_at: datetime

    class Config:
        from_attributes = True


# ── Manual grading (examiner) ───────────────────────────────────────────────────
class GradeItem(BaseModel):
    response_id: UUID
    marks_awarded: float

class GradeRequest(BaseModel):
    grades: List[GradeItem]

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