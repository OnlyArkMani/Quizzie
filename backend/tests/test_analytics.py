"""
Analytics endpoint tests — summary, leaderboard, student stats, export.
"""
import pytest
from unittest.mock import patch
from datetime import timedelta


def _submit_attempt(client, student_headers, exam, question, correct_opt):
    """Helper: start + submit an attempt with a correct answer."""
    attempt_id = client.post("/api/v1/attempts/start",
                             json={"exam_id": str(exam.id)},
                             headers=student_headers).json()["id"]
    with patch("app.api.v1.attempts.evaluate_attempt_task") as m:
        m.apply_async.side_effect = Exception("no celery")
        client.post(f"/api/v1/attempts/{attempt_id}/submit", json={
            "responses": [{
                "question_id": str(question.id),
                "selected_option_ids": [str(correct_opt.id)],
                "marked_for_review": False,
            }]
        }, headers=student_headers)
    return attempt_id


class TestAnalytics:
    def test_exam_summary(self, client, examiner_headers, student_headers, live_exam):
        exam, question, correct_opt, _ = live_exam
        _submit_attempt(client, student_headers, exam, question, correct_opt)

        r = client.get(f"/api/v1/analytics/exam/{exam.id}/summary",
                       headers=examiner_headers)
        assert r.status_code == 200
        data = r.json()
        assert data["total_attempts"] == 1
        assert float(data["highest_score"]) == 100.0
        assert "score_distribution" in data
        assert "topic_wise_stats" in data

    def test_summary_empty_exam(self, client, examiner_headers, live_exam):
        exam, *_ = live_exam
        r = client.get(f"/api/v1/analytics/exam/{exam.id}/summary",
                       headers=examiner_headers)
        assert r.status_code == 200
        assert r.json()["total_attempts"] == 0

    def test_leaderboard(self, client, examiner_headers, student_headers, live_exam):
        exam, question, correct_opt, _ = live_exam
        _submit_attempt(client, student_headers, exam, question, correct_opt)

        r = client.get(f"/api/v1/analytics/exam/{exam.id}/leaderboard",
                       headers=examiner_headers)
        assert r.status_code == 200
        board = r.json()
        assert len(board) >= 1
        assert board[0]["rank"] == 1
        assert "student_name" in board[0]

    def test_student_cannot_see_summary(self, client, student_headers, live_exam):
        exam, *_ = live_exam
        r = client.get(f"/api/v1/analytics/exam/{exam.id}/summary",
                       headers=student_headers)
        assert r.status_code == 403

    def test_student_own_stats(self, client, student_headers, live_exam):
        r = client.get("/api/v1/analytics/student/me/stats",
                       headers=student_headers)
        assert r.status_code == 200
        data = r.json()
        assert "totalExams" in data
        assert "averageScore" in data

    def test_examiner_stats(self, client, examiner_headers, live_exam):
        r = client.get("/api/v1/analytics/examiner/stats",
                       headers=examiner_headers)
        assert r.status_code == 200
        data = r.json()
        assert "totalExams" in data
        assert data["totalExams"] >= 1

    def test_csv_export(self, client, examiner_headers, student_headers, live_exam):
        exam, question, correct_opt, _ = live_exam
        _submit_attempt(client, student_headers, exam, question, correct_opt)

        r = client.get(f"/api/v1/analytics/exam/{exam.id}/export",
                       headers=examiner_headers)
        assert r.status_code == 200
        assert "text/csv" in r.headers["content-type"]
        lines = r.text.strip().split("\n")
        assert len(lines) >= 2   # header + at least one data row
        assert "Student Name" in lines[0]
