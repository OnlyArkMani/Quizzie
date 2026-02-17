"""
fix_stuck_attempts.py

Run this once to clean up stuck 'in_progress' exam attempts
that prevent students from starting new exams.
"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.core.database import SessionLocal
from app.models.attempt import ExamAttempt, AttemptStatus


def fix_stuck_attempts():
    db = SessionLocal()
    try:
        # Find all IN_PROGRESS attempts
        stuck_attempts = db.query(ExamAttempt).filter(
            ExamAttempt.status == AttemptStatus.IN_PROGRESS
        ).all()

        print(f"Found {len(stuck_attempts)} stuck in_progress attempts")

        for attempt in stuck_attempts:
            print(
                f"  Fixing attempt {str(attempt.id)[:8]} "
                f"for exam {str(attempt.exam_id)[:8]}"
            )

            # ✅ Move to a VALID enum state
            attempt.status = AttemptStatus.SUBMITTED
            attempt.submitted_at = datetime.utcnow()

        db.commit()
        print(f"\n✅ Successfully fixed {len(stuck_attempts)} stuck attempts")

    except Exception as e:
        db.rollback()
        print(f"❌ Error while fixing attempts: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    fix_stuck_attempts()
