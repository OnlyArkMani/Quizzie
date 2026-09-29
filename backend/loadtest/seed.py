"""
Seed a benchmark database: 1 examiner, N students, one LIVE exam with Q
questions x 4 options. Writes tokens + ids to loadtest/fixture.json.

    DATABASE_URL=postgresql://.../quizzie_bench python -m loadtest.seed --students 500
"""
import argparse
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path

from app.core.database import Base, SessionLocal, engine
from app.core.security import create_access_token
import app.models  # noqa: F401
from app.models.exam import Exam, ExamStatus
from app.models.question import Option, Question, QuestionType
from app.models.user import User, UserRole

OUT = Path(__file__).with_name("fixture.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--students", type=int, default=500)
    ap.add_argument("--questions", type=int, default=30)
    args = ap.parse_args()

    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    tag = uuid.uuid4().hex[:6]
    # Password hashing is irrelevant to the benchmark; tokens are minted directly.
    examiner = User(email=f"examiner-{tag}@bench", password_hash="x", full_name="Examiner",
                    role=UserRole.EXAMINER, is_verified=True)
    db.add(examiner)
    db.commit()
    exam = Exam(title="Bench exam", description="", duration_minutes=180,
                total_marks=args.questions, pass_percentage=40,
                status=ExamStatus.LIVE, created_by=examiner.id)
    db.add(exam)
    db.commit()
    questions = []
    for i in range(args.questions):
        q = Question(exam_id=exam.id, question_text=f"Q{i}?", question_type=QuestionType.SINGLE,
                     marks=1, topic=f"T{i % 5}", display_order=i)
        db.add(q)
        db.flush()
        opts = [Option(question_id=q.id, option_text=f"o{j}", is_correct=(j == 0), display_order=j)
                for j in range(4)]
        db.add_all(opts)
        db.flush()
        questions.append({"id": str(q.id), "options": [str(o.id) for o in opts]})
    students = [User(email=f"s{i}-{tag}@bench", password_hash="x", full_name=f"S{i}",
                     role=UserRole.STUDENT, is_verified=True) for i in range(args.students)]
    db.add_all(students)
    db.commit()

    ttl = timedelta(hours=6)
    fixture = {
        "exam_id": str(exam.id),
        "examiner_token": create_access_token({"sub": examiner.email}, ttl),
        "student_tokens": [create_access_token({"sub": s.email}, ttl) for s in students],
        "questions": questions,
    }
    OUT.write_text(json.dumps(fixture))
    print(f"seeded exam {exam.id} with {args.students} students -> {OUT}")


if __name__ == "__main__":
    main()
