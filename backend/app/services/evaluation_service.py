"""
EvaluationService — fixed N+1.

Old code: for each response → query Question → query Options (N×M queries).
New code: one JOIN query loads all questions + options in a single round-trip.
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select
from uuid import UUID
from typing import Dict

from app.models.attempt import ExamAttempt, Response, AttemptStatus
from app.models.question import Question, Option, MANUAL_QUESTION_TYPES
from app.models.exam import Exam


def _qtype(question) -> str:
    qt = question.question_type
    return qt.value if hasattr(qt, "value") else str(qt)


class EvaluationService:
    def __init__(self, db: Session):
        self.db = db

    def evaluate_attempt(self, attempt_id: UUID) -> Dict:
        attempt = self.db.query(ExamAttempt).filter(ExamAttempt.id == attempt_id).first()
        if not attempt:
            raise ValueError("Attempt not found")

        exam = self.db.query(Exam).filter(Exam.id == attempt.exam_id).first()

        # ── Single query: all responses + their questions + options ───────────
        responses = (
            self.db.query(Response)
            .filter(Response.attempt_id == attempt_id)
            .all()
        )

        question_ids = [r.question_id for r in responses]

        # Load all questions and their options in ONE query
        questions = (
            self.db.query(Question)
            .options(joinedload(Question.options))
            .filter(Question.id.in_(question_ids))
            .all()
        )
        question_map: Dict[UUID, Question] = {q.id: q for q in questions}

        # Pre-build correct-option sets per question (no per-response DB hit)
        correct_opts: Dict[UUID, set] = {
            q.id: {opt.id for opt in q.options if opt.is_correct}
            for q in questions
        }

        total_marks = 0
        obtained_marks = 0.0
        correct_count = 0
        pending_grading = 0
        topic_stats: Dict[str, Dict] = {}

        for response in responses:
            question = question_map.get(response.question_id)
            if not question:
                continue

            total_marks += question.marks

            # Coding/subjective: graded manually by an examiner. Never auto-score
            # or overwrite an examiner's marks — just tally what's already graded
            # and flag the rest as pending.
            if _qtype(question) in MANUAL_QUESTION_TYPES:
                if response.marks_awarded is not None:
                    obtained_marks += float(response.marks_awarded)
                else:
                    pending_grading += 1
                continue

            selected = set(response.selected_option_ids or [])
            correct = correct_opts.get(question.id, set())

            is_correct = bool(correct) and correct == selected
            marks = question.marks if is_correct else 0

            response.is_correct = is_correct
            response.marks_awarded = marks

            if is_correct:
                obtained_marks += marks
                correct_count += 1

            if question.topic:
                if question.topic not in topic_stats:
                    topic_stats[question.topic] = {"correct": 0, "total": 0}
                topic_stats[question.topic]["total"] += 1
                if is_correct:
                    topic_stats[question.topic]["correct"] += 1

        attempt.score = (obtained_marks / total_marks * 100) if total_marks > 0 else 0
        attempt.status = AttemptStatus.EVALUATED

        self.db.commit()

        return {
            "score": float(attempt.score),
            "obtained_marks": float(obtained_marks),
            "total_marks": total_marks,
            "correct_count": correct_count,
            "needs_grading": pending_grading > 0,
            "pending_grading": pending_grading,
            "topic_wise": topic_stats,
        }
