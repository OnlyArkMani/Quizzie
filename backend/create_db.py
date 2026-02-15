"""
Seed database with sample data for testing
"""
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.user import User
from app.models.exam import Exam
from app.models.question import Question, Option

def seed_db():
    db = SessionLocal()
    
    try:
        print("Seeding database...")
        
        # Check if users already exist
        existing_student = db.query(User).filter(User.email == "student@demo.com").first()
        if existing_student:
            print("⚠️  Data already exists, skipping seed...")
            return
        
        # Create sample users with shorter passwords
        student = User(
            email="student@demo.com",
            password_hash=get_password_hash("pass123"),  # Shorter password
            full_name="John Student",
            role="student"
        )
        
        examiner = User(
            email="examiner@demo.com",
            password_hash=get_password_hash("pass123"),  # Shorter password
            full_name="Jane Examiner",
            role="examiner"
        )
        
        db.add(student)
        db.add(examiner)
        db.commit()
        db.refresh(examiner)
        
        print(" Users created")
        
        # Create sample exam
        exam = Exam(
            title="Data Structures Final Exam",
            description="Comprehensive exam covering arrays, linked lists, trees, and graphs",
            duration_minutes=90,
            total_marks=100,
            pass_percentage=40,
            status="live",
            created_by=examiner.id
        )
        
        db.add(exam)
        db.commit()
        db.refresh(exam)
        
        print(" Exam created")
        
        # Create sample questions
        question1 = Question(
            exam_id=exam.id,
            question_text="What is the time complexity of binary search?",
            question_type="single",
            marks=5,
            topic="Algorithms",
            display_order=0
        )
        
        db.add(question1)
        db.flush()
        
        # Add options for question 1
        options1 = [
            Option(question_id=question1.id, option_text="O(n)", is_correct=False, display_order=0),
            Option(question_id=question1.id, option_text="O(log n)", is_correct=True, display_order=1),
            Option(question_id=question1.id, option_text="O(n²)", is_correct=False, display_order=2),
            Option(question_id=question1.id, option_text="O(1)", is_correct=False, display_order=3),
        ]
        
        for opt in options1:
            db.add(opt)
        
        # Question 2
        question2 = Question(
            exam_id=exam.id,
            question_text="Which data structures use LIFO principle?",
            question_type="multiple",
            marks=5,
            topic="Data Structures",
            display_order=1
        )
        
        db.add(question2)
        db.flush()
        
        options2 = [
            Option(question_id=question2.id, option_text="Stack", is_correct=True, display_order=0),
            Option(question_id=question2.id, option_text="Queue", is_correct=False, display_order=1),
            Option(question_id=question2.id, option_text="Recursion Call Stack", is_correct=True, display_order=2),
            Option(question_id=question2.id, option_text="Array", is_correct=False, display_order=3),
        ]
        
        for opt in options2:
            db.add(opt)
        
        # Question 3
        question3 = Question(
            exam_id=exam.id,
            question_text="What is the best case time complexity of Quick Sort?",
            question_type="single",
            marks=5,
            topic="Algorithms",
            display_order=2
        )
        
        db.add(question3)
        db.flush()
        
        options3 = [
            Option(question_id=question3.id, option_text="O(n)", is_correct=False, display_order=0),
            Option(question_id=question3.id, option_text="O(n log n)", is_correct=True, display_order=1),
            Option(question_id=question3.id, option_text="O(n²)", is_correct=False, display_order=2),
            Option(question_id=question3.id, option_text="O(log n)", is_correct=False, display_order=3),
        ]
        
        for opt in options3:
            db.add(opt)
        
        db.commit()
        
        print(" Questions created")
        print("\n Database seeded successfully!")
        print("\n Test Credentials:")
        print("   Student: student@demo.com / pass123")
        print("   Examiner: examiner@demo.com / pass123")
        
    except Exception as e:
        print(f" Error seeding database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_db()