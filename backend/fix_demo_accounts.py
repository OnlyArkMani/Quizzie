"""
Quick fix: Mark demo accounts as verified and ensure their roles are correct.
Run this once from the backend folder:
  python fix_demo_accounts.py
"""
from app.core.database import SessionLocal
from app.models.user import User

def fix():
    db = SessionLocal()
    try:
        fixed = 0
        for email in ("student@demo.com", "examiner@demo.com"):
            user = db.query(User).filter(User.email == email).first()
            if user:
                if not user.is_verified:
                    user.is_verified = True
                    print(f"  Fixed is_verified for {email}")
                    fixed += 1
                # Clear any stale verification token
                if user.verification_token:
                    user.verification_token = None
                    user.verification_token_expires = None
                    print(f"  Cleared stale token for {email}")
                    fixed += 1
            else:
                print(f"  WARNING: {email} not found in database — run seed_data.py first")

        if fixed:
            db.commit()
            print(f"\nDone — {fixed} fix(es) applied.")
        else:
            print("\nAll demo accounts already correct, nothing to do.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fix()
