"""
cleanup_users.py — Remove all non-demo users from the database.

Keeps ONLY:
  - student@demo.com
  - examiner@demo.com

Also deletes all data owned by removed users (exams, attempts, etc.)
via CASCADE if foreign keys are set up, otherwise manually.

Run from the backend directory (with venv active):
    python cleanup_users.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)

KEEP_EMAILS = {"student@demo.com", "examiner@demo.com"}


def main():
    print("\n🧹 Quizzie User Cleanup")
    print("=" * 45)
    print(f"  Keeping only: {', '.join(sorted(KEEP_EMAILS))}")
    print()

    with engine.begin() as conn:
        # Show what will be deleted
        rows = conn.execute(text(
            "SELECT id, email, role, is_verified FROM users ORDER BY created_at"
        )).fetchall()

        if not rows:
            print("  No users in the database.")
            return

        print(f"  Found {len(rows)} user(s) in DB:")
        to_delete = []
        for row in rows:
            uid, email, role, verified = row
            keep = email in KEEP_EMAILS
            tag = "✅ KEEP" if keep else "🗑️  DELETE"
            print(f"    {tag}  {email}  ({role})  verified={verified}")
            if not keep:
                to_delete.append((uid, email))

        if not to_delete:
            print("\n  Nothing to delete — only demo users exist.")
            # Still make sure demo users are verified
            _ensure_demo_verified(conn)
            return

        print(f"\n  Deleting {len(to_delete)} user(s)...")

        for uid, email in to_delete:
            # Delete cascade: exams → questions/options → attempts → responses/cheat_logs
            # If FK constraints are ON DELETE CASCADE this happens automatically.
            # We do it explicitly to be safe in case CASCADE isn't set.

            # 1. Get exam ids owned by this user
            exam_ids = [r[0] for r in conn.execute(
                text("SELECT id FROM exams WHERE created_by = :uid"),
                {"uid": uid}
            ).fetchall()]

            for eid in exam_ids:
                # Delete attempts and their responses for this exam
                attempt_ids = [r[0] for r in conn.execute(
                    text("SELECT id FROM exam_attempts WHERE exam_id = :eid"),
                    {"eid": eid}
                ).fetchall()]
                for aid in attempt_ids:
                    conn.execute(text("DELETE FROM responses WHERE attempt_id = :aid"), {"aid": aid})
                    conn.execute(text("DELETE FROM cheat_logs WHERE attempt_id = :aid"), {"aid": aid})
                conn.execute(text("DELETE FROM exam_attempts WHERE exam_id = :eid"), {"eid": eid})

                # Delete questions and options
                q_ids = [r[0] for r in conn.execute(
                    text("SELECT id FROM questions WHERE exam_id = :eid"),
                    {"eid": eid}
                ).fetchall()]
                for qid in q_ids:
                    conn.execute(text("DELETE FROM options WHERE question_id = :qid"), {"qid": qid})
                conn.execute(text("DELETE FROM questions WHERE exam_id = :eid"), {"eid": eid})

                # Delete proctoring settings
                conn.execute(text("DELETE FROM proctoring_settings WHERE exam_id = :eid"), {"eid": eid})

            # Delete all exams by this user
            conn.execute(text("DELETE FROM exams WHERE created_by = :uid"), {"uid": uid})

            # Delete attempts where this user was the STUDENT
            attempt_ids = [r[0] for r in conn.execute(
                text("SELECT id FROM exam_attempts WHERE student_id = :uid"),
                {"uid": uid}
            ).fetchall()]
            for aid in attempt_ids:
                conn.execute(text("DELETE FROM responses WHERE attempt_id = :aid"), {"aid": aid})
                conn.execute(text("DELETE FROM cheat_logs WHERE attempt_id = :aid"), {"aid": aid})
            conn.execute(text("DELETE FROM exam_attempts WHERE student_id = :uid"), {"uid": uid})

            # Finally delete the user
            conn.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": uid})
            print(f"    ✅ Deleted: {email}")

        # Ensure demo users are verified
        _ensure_demo_verified(conn)

    print("\n✅ Cleanup complete!\n")


def _ensure_demo_verified(conn):
    """Make sure demo accounts have is_verified = true."""
    for email in KEEP_EMAILS:
        result = conn.execute(
            text("UPDATE users SET is_verified = true WHERE email = :email AND is_verified = false"),
            {"email": email}
        )
        if result.rowcount > 0:
            print(f"\n  ✅ Fixed: {email} marked as verified")


if __name__ == "__main__":
    main()
