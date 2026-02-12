from pydantic import BaseModel
from typing import Dict, List, Optional

class TopicStats(BaseModel):
    correct: int
    total: int
    percentage: float

class ExamSummary(BaseModel):
    total_attempts: int
    average_score: float
    highest_score: float
    lowest_score: float
    pass_percentage: float
    topic_wise_stats: Dict[str, TopicStats]

class LeaderboardEntry(BaseModel):
    student_name: str
    score: float
    time_taken_seconds: int
    rank: int

class StudentPerformance(BaseModel):
    total_exams: int
    average_score: float
    exams_taken: int
    topic_wise: Dict[str, TopicStats]