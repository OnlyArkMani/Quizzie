"""
Database initialization script
Run this to create all tables
"""
from app.core.database import engine, Base
from app.models import User, Exam, Question, Option, ExamAttempt, Response, CheatLog

def init_db():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables created successfully!")

if __name__ == "__main__":
    init_db()