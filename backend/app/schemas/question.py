from pydantic import BaseModel
from typing import Optional, List
from uuid import UUID

class OptionCreate(BaseModel):
    option_text: str
    is_correct: bool
    display_order: int = 0  # ✅ Default value - no longer required from frontend

class Option(OptionCreate):
    id: UUID
    question_id: UUID

    class Config:
        from_attributes = True

class QuestionCreate(BaseModel):
    question_text: str
    question_type: str = "single"
    marks: int = 1
    topic: Optional[str] = None
    display_order: int = 0
    options: List[OptionCreate]

class Question(QuestionCreate):
    id: UUID
    exam_id: UUID
    options: List[Option] = []

    class Config:
        from_attributes = True