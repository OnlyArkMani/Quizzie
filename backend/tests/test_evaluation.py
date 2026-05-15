"""
Unit tests for EvaluationService — core scoring logic.
Uses only the DB session, no HTTP layer.
"""
import pytest
from app.services.evaluation_service import EvaluationService
from app.models.attempt import ExamAttempt, Response, AttemptStatus
from app.models.question import Question, Option, QuestionType
from app.models.exam import Exam, ExamStatus


class TestEvaluationService:
    def test_all_correct(self, db, examiner_user, student_user):
        exam = Exam(title="E", description="", duration_minutes=30, total_marks=20,
                    pass_percentage=40, status=ExamStatus.LIVE, created_by=examiner_user.id)
        db.add(exam)
        db.commit()

        q1 = Question(exam_id=exam.id, question_text="Q1", question_type=QuestionType.SINGLE,
                      marks=10, topic="A", display_order=1)
        q2 = Question(exam_id=exam.id, question_text="Q2", question_type=QuestionType.SINGLE,
                      marks=10, topic="B", display_order=2)
        db.add_all([q1, q2])
        db.commit()

        o1c = Option(question_id=q1.id, option_text="Right", is_correct=True, display_order=1)
        o1w = Option(question_id=q1.id, option_text="Wrong", is_correct=False, display_order=2)
        o2c = Option(question_id=q2.id, option_text="Right", is_correct=True, display_order=1)
        db.add_all([o1c, o1w, o2c])
        db.commit()

        # Use real student_user — satisfies exam_attempts_student_id_fkey constraint
        attempt = ExamAttempt(exam_id=exam.id, student_id=student_user.id,
                              status=AttemptStatus.SUBMITTED)
        db.add(attempt)
        db.commit()

        db.add(Response(attempt_id=attempt.id, question_id=q1.id,
                        selected_option_ids=[o1c.id], marked_for_review=False))
        db.add(Response(attempt_id=attempt.id, question_id=q2.id,
                        selected_option_ids=[o2c.id], marked_for_review=False))
        db.commit()

        svc = EvaluationService(db)
        result = svc.evaluate_attempt(attempt.id)

        assert result["score"] == 100.0
        assert result["correct_count"] == 2
        assert result["obtained_marks"] == 20

    def test_all_wrong(self, db, examiner_user, student_user):
        exam = Exam(title="E2", description="", duration_minutes=30, total_marks=10,
                    pass_percentage=40, status=ExamStatus.LIVE, created_by=examiner_user.id)
        db.add(exam)
        db.commit()

        q = Question(exam_id=exam.id, question_text="Q", question_type=QuestionType.SINGLE,
                     marks=10, display_order=1)
        db.add(q)
        db.commit()

        oc = Option(question_id=q.id, option_text="Right", is_correct=True, display_order=1)
        ow = Option(question_id=q.id, option_text="Wrong", is_correct=False, display_order=2)
        db.add_all([oc, ow])
        db.commit()

        attempt = ExamAttempt(exam_id=exam.id, student_id=student_user.id,
                              status=AttemptStatus.SUBMITTED)
        db.add(attempt)
        db.commit()

        db.add(Response(attempt_id=attempt.id, question_id=q.id,
                        selected_option_ids=[ow.id], marked_for_review=False))
        db.commit()

        result = EvaluationService(db).evaluate_attempt(attempt.id)
        assert result["score"] == 0.0
        assert result["correct_count"] == 0

    def test_status_set_to_evaluated(self, db, examiner_user, student_user):
        exam = Exam(title="E3", description="", duration_minutes=30, total_marks=5,
                    pass_percentage=40, status=ExamStatus.LIVE, created_by=examiner_user.id)
        db.add(exam)
        db.commit()

        q = Question(exam_id=exam.id, question_text="Q", question_type=QuestionType.SINGLE,
                     marks=5, display_order=1)
        db.add(q)
        db.commit()

        oc = Option(question_id=q.id, option_text="R", is_correct=True, display_order=1)
        db.add(oc)
        db.commit()

        attempt = ExamAttempt(exam_id=exam.id, student_id=student_user.id,
                              status=AttemptStatus.SUBMITTED)
        db.add(attempt)
        db.commit()

        db.add(Response(attempt_id=attempt.id, question_id=q.id,
                        selected_option_ids=[oc.id], marked_for_review=False))
        db.commit()

        EvaluationService(db).evaluate_attempt(attempt.id)
        db.refresh(attempt)
        assert attempt.status == AttemptStatus.EVALUATED
