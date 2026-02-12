from pydantic import BaseModel
from typing import List, Optional
from uuid import UUID

class OptionBase(BaseModel):
    option_text: str
    is_correct: bool
    display_order: int

class OptionCreate(OptionBase):
    pass

class Option(OptionBase):
    id: UUID
    question_id: UUID
    
    class Config:
        from_attributes = True

class QuestionBase(BaseModel):
    question_text: str
    question_type: str
    marks: int
    topic: Optional[str] = None
    display_order: int

class QuestionCreate(QuestionBase):
    options: List[OptionCreate]

class Question(QuestionBase):
    id: UUID
    exam_id: UUID
    options: List[Option] = []
    
    class Config:
        from_attributes = True