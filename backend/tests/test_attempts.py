"""
Attempt endpoint tests — start, submit, results, auto-save.
Evaluation runs synchronously in tests (no Celery needed).
"""
import pytest
from unittest.mock import patch, MagicMock


class TestStartExam:
    def test_start_live_exam(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        r = client.post("/api/v1/attempts/start", json={"exam_id": str(exam.id)},
                        headers=student_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["exam_id"] == str(exam.id)
        assert data["status"] == "in_progress"

    def test_resume_in_progress_attempt(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        r1 = client.post("/api/v1/attempts/start", json={"exam_id": str(exam.id)},
                         headers=student_headers)
        r2 = client.post("/api/v1/attempts/start", json={"exam_id": str(exam.id)},
                         headers=student_headers)
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["id"] == r2.json()["id"]  # same attempt returned

    def test_start_draft_exam_fails(self, client, student_headers, db, examiner_user):
        from app.models.exam import Exam, ExamStatus
        draft = Exam(title="D", description="", duration_minutes=30, total_marks=10,
                     pass_percentage=40, status=ExamStatus.DRAFT, created_by=examiner_user.id)
        db.add(draft)
        db.commit()
        r = client.post("/api/v1/attempts/start", json={"exam_id": str(draft.id)},
                        headers=student_headers)
        assert r.status_code == 400

    def test_student_cannot_start_as_examiner(self, client, examiner_headers, live_exam):
        exam, *_ = live_exam
        r = client.post("/api/v1/attempts/start", json={"exam_id": str(exam.id)},
                        headers=examiner_headers)
        assert r.status_code == 403


class TestSubmitExam:
    def _start(self, client, headers, exam_id):
        r = client.post("/api/v1/attempts/start", json={"exam_id": str(exam_id)},
                        headers=headers)
        assert r.status_code == 201
        return r.json()["id"]

    def test_submit_correct_answer(self, client, student_headers, live_exam):
        exam, question, correct_opt, wrong_opt = live_exam
        attempt_id = self._start(client, student_headers, exam.id)

        # Patch Celery so it falls back to sync evaluation in tests
        with patch("app.api.v1.attempts.evaluate_attempt_task") as mock_task:
            mock_task.apply_async.side_effect = Exception("no celery in tests")
            r = client.post(f"/api/v1/attempts/{attempt_id}/submit", json={
                "responses": [{
                    "question_id": str(question.id),
                    "selected_option_ids": [str(correct_opt.id)],
                    "marked_for_review": False,
                }]
            }, headers=student_headers)
        assert r.status_code == 200
        data = r.json()
        assert float(data["score"]) == 100.0
        assert data["correct_count"] == 1

    def test_submit_wrong_answer(self, client, student_headers, live_exam):
        exam, question, correct_opt, wrong_opt = live_exam
        attempt_id = self._start(client, student_headers, exam.id)

        with patch("app.api.v1.attempts.evaluate_attempt_task") as mock_task:
            mock_task.apply_async.side_effect = Exception("no celery in tests")
            r = client.post(f"/api/v1/attempts/{attempt_id}/submit", json={
                "responses": [{
                    "question_id": str(question.id),
                    "selected_option_ids": [str(wrong_opt.id)],
                    "marked_for_review": False,
                }]
            }, headers=student_headers)
        assert r.status_code == 200
        assert float(r.json()["score"]) == 0.0

    def test_double_submit_rejected(self, client, student_headers, live_exam):
        exam, question, correct_opt, _ = live_exam
        attempt_id = self._start(client, student_headers, exam.id)
        payload = {"responses": [{
            "question_id": str(question.id),
            "selected_option_ids": [str(correct_opt.id)],
            "marked_for_review": False,
        }]}

        with patch("app.api.v1.attempts.evaluate_attempt_task") as mock_task:
            mock_task.apply_async.side_effect = Exception("no celery in tests")
            client.post(f"/api/v1/attempts/{attempt_id}/submit", json=payload, headers=student_headers)
            r2 = client.post(f"/api/v1/attempts/{attempt_id}/submit", json=payload, headers=student_headers)
        assert r2.status_code == 400

    def test_submit_other_students_attempt_forbidden(self, client, student_headers, examiner_headers, live_exam, db, examiner_user):
        from app.models.user import User, UserRole
        from app.core.security import get_password_hash, create_access_token
        from datetime import timedelta

        other = User(email="other@test.com", password_hash=get_password_hash("pw"),
                     full_name="Other", role=UserRole.STUDENT, is_verified=True)
        db.add(other)
        db.commit()
        other_token = create_access_token({"sub": other.email}, timedelta(minutes=30))
        other_headers = {"Authorization": f"Bearer {other_token}"}

        exam, question, correct_opt, _ = live_exam
        attempt_id = self._start(client, student_headers, exam.id)

        r = client.post(f"/api/v1/attempts/{attempt_id}/submit", json={
            "responses": [{"question_id": str(question.id),
                           "selected_option_ids": [str(correct_opt.id)],
                           "marked_for_review": False}]
        }, headers=other_headers)
        assert r.status_code == 403


class TestMyAttempts:
    def test_get_my_attempts(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        client.post("/api/v1/attempts/start", json={"exam_id": str(exam.id)},
                    headers=student_headers)
        r = client.get("/api/v1/attempts/my-attempts", headers=student_headers)
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_auto_save(self, client, student_headers, live_exam):
        exam, question, opt, _ = live_exam
        attempt_id = client.post("/api/v1/attempts/start", json={"exam_id": str(exam.id)},
                                 headers=student_headers).json()["id"]
        r = client.post(f"/api/v1/attempts/{attempt_id}/auto-save", json={
            "responses": [{"question_id": str(question.id),
                           "selected_option_ids": [str(opt.id)]}]
        }, headers=student_headers)
        assert r.status_code == 200
        assert r.json()["saved"] == 1
