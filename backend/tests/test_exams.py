"""
Exam endpoint tests — CRUD, status transitions, questions with cache.
"""
import pytest


class TestExamCRUD:
    def test_create_exam_as_examiner(self, client, examiner_headers):
        r = client.post("/api/v1/exams/", json={
            "title": "Chemistry Test",
            "description": "Organic chemistry",
            "duration_minutes": 90,
            "total_marks": 100,
            "pass_percentage": 40,
        }, headers=examiner_headers)
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "draft"
        assert data["title"] == "Chemistry Test"

    def test_create_exam_as_student_forbidden(self, client, student_headers):
        r = client.post("/api/v1/exams/", json={
            "title": "Sneaky Exam",
            "description": "...",
            "duration_minutes": 30,
            "total_marks": 50,
            "pass_percentage": 40,
        }, headers=student_headers)
        assert r.status_code == 403

    def test_list_exams_examiner_sees_own(self, client, examiner_headers, live_exam):
        r = client.get("/api/v1/exams/", headers=examiner_headers)
        assert r.status_code == 200
        ids = [e["id"] for e in r.json()]
        exam, *_ = live_exam
        assert str(exam.id) in ids

    def test_list_exams_student_sees_only_live(self, client, student_headers, live_exam, db):
        from app.models.exam import Exam, ExamStatus
        from app.models.user import User, UserRole
        from app.core.security import get_password_hash

        # Create a draft exam — student should NOT see it
        examiner2 = User(
            email="ex2@test.com", password_hash=get_password_hash("pw"),
            full_name="Ex2", role=UserRole.EXAMINER, is_verified=True,
        )
        db.add(examiner2)
        db.commit()
        draft = Exam(
            title="Draft", description="", duration_minutes=30,
            total_marks=10, pass_percentage=40,
            status=ExamStatus.DRAFT, created_by=examiner2.id,
        )
        db.add(draft)
        db.commit()

        r = client.get("/api/v1/exams/", headers=student_headers)
        assert r.status_code == 200
        statuses = {e["status"] for e in r.json()}
        assert statuses <= {"live"}

    def test_get_exam_detail(self, client, examiner_headers, live_exam):
        exam, *_ = live_exam
        r = client.get(f"/api/v1/exams/{exam.id}", headers=examiner_headers)
        assert r.status_code == 200
        assert r.json()["id"] == str(exam.id)

    def test_get_nonexistent_exam(self, client, examiner_headers):
        import uuid
        r = client.get(f"/api/v1/exams/{uuid.uuid4()}", headers=examiner_headers)
        assert r.status_code == 404

    def test_status_transition_to_live(self, client, examiner_headers, db, examiner_user):
        from app.models.exam import Exam, ExamStatus
        exam = Exam(
            title="Transition Test", description="", duration_minutes=30,
            total_marks=10, pass_percentage=40,
            status=ExamStatus.DRAFT, created_by=examiner_user.id,
        )
        db.add(exam)
        db.commit()

        r = client.patch(
            f"/api/v1/exams/{exam.id}/status?status=live",
            headers=examiner_headers,
        )
        assert r.status_code == 200
        assert r.json()["status"] == "live"

    def test_get_exam_questions_cached(self, client, student_headers, live_exam):
        exam, q, correct, wrong = live_exam
        r = client.get(f"/api/v1/exams/{exam.id}/questions", headers=student_headers)
        assert r.status_code == 200
        questions = r.json()
        assert len(questions) == 1
        assert questions[0]["question_text"] == "What is 2 + 2?"
        assert len(questions[0]["options"]) == 2
