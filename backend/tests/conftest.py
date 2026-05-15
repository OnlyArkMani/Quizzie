"""
Shared pytest fixtures for Quizzie test suite.
Uses a real PostgreSQL test DB (same engine as prod) and rolls back after each test.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
import os

# ── Test DB URL (use env var or fallback to local) ─────────────────────────────
TEST_DB_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres123@localhost:5432/quizzie_test"
)

# Override before importing app so config picks it up
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["REDIS_URL"] = "redis://localhost:6379/1"   # DB 1 for tests
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-only"
os.environ["ENVIRONMENT"] = "test"


from app.core.database import Base, get_db
from app.main import app
from app.models.user import User, UserRole
from app.models.exam import Exam, ExamStatus
from app.models.question import Question, Option, QuestionType
from app.models.attempt import ExamAttempt, AttemptStatus
from app.core.security import get_password_hash, create_access_token
from datetime import timedelta


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(TEST_DB_URL, pool_pre_ping=True)
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)


@pytest.fixture(scope="function")
def db(engine):
    """Each test gets a fresh transaction that is rolled back after."""
    connection = engine.connect()
    transaction = connection.begin()
    TestingSession = sessionmaker(bind=connection)
    session = TestingSession()

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(db):
    """TestClient with DB dependency overridden to use test session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c
    app.dependency_overrides.clear()


# ── User fixtures ─────────────────────────────────────────────────────────────

@pytest.fixture
def student_user(db):
    user = User(
        email="student@test.com",
        password_hash=get_password_hash("password123"),
        full_name="Test Student",
        role=UserRole.STUDENT,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def examiner_user(db):
    user = User(
        email="examiner@test.com",
        password_hash=get_password_hash("password123"),
        full_name="Test Examiner",
        role=UserRole.EXAMINER,
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def make_token(user: User) -> str:
    return create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=120),
    )


@pytest.fixture
def student_headers(student_user):
    return {"Authorization": f"Bearer {make_token(student_user)}"}


@pytest.fixture
def examiner_headers(examiner_user):
    return {"Authorization": f"Bearer {make_token(examiner_user)}"}


# ── Exam + Question fixtures ───────────────────────────────────────────────────

@pytest.fixture
def live_exam(db, examiner_user):
    exam = Exam(
        title="Physics Test",
        description="Unit test exam",
        duration_minutes=60,
        total_marks=10,
        pass_percentage=40,
        status=ExamStatus.LIVE,
        created_by=examiner_user.id,
    )
    db.add(exam)
    db.commit()
    db.refresh(exam)

    q = Question(
        exam_id=exam.id,
        question_text="What is 2 + 2?",
        question_type=QuestionType.SINGLE,
        marks=10,
        topic="Math",
        display_order=1,
    )
    db.add(q)
    db.commit()
    db.refresh(q)

    correct = Option(question_id=q.id, option_text="4", is_correct=True, display_order=1)
    wrong   = Option(question_id=q.id, option_text="5", is_correct=False, display_order=2)
    db.add_all([correct, wrong])
    db.commit()
    db.refresh(correct)

    return exam, q, correct, wrong
