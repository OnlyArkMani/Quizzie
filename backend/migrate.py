"""
migrate.py — Safe one-shot migration runner for Quizzie.

Handles the common situation where tables were created via SQLAlchemy's
create_all() BEFORE Alembic was set up, so alembic_version is empty.

Run from the backend directory:
    python migrate.py
"""
import sys
import os

# Make sure we can import app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import create_engine, text, inspect
from app.core.config import settings

engine = create_engine(settings.DATABASE_URL)


def get_current_revision() -> str | None:
    with engine.connect() as conn:
        try:
            row = conn.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
            return row[0] if row else None
        except Exception:
            return None


def table_exists(conn, table_name: str) -> bool:
    return inspect(conn).has_table(table_name)


def column_exists(conn, table_name: str, column_name: str) -> bool:
    cols = [c["name"] for c in inspect(conn).get_columns(table_name)]
    return column_name in cols


def stamp_revision(revision: str):
    """Mark a migration as applied without running it (for tables already created)."""
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
        conn.execute(text("DELETE FROM alembic_version"))
        conn.execute(text(f"INSERT INTO alembic_version VALUES ('{revision}')"))
    print(f"  ✅ Stamped alembic_version = '{revision}'")


def apply_email_verification_columns():
    """Manually add the email-verification columns that add_email_verification migration adds."""
    new_columns = {
        "is_verified":                 "ALTER TABLE users ADD COLUMN is_verified BOOLEAN NOT NULL DEFAULT false",
        "verification_token":          "ALTER TABLE users ADD COLUMN verification_token VARCHAR(255)",
        "verification_token_expires":  "ALTER TABLE users ADD COLUMN verification_token_expires TIMESTAMP",
        "reset_token":                 "ALTER TABLE users ADD COLUMN reset_token VARCHAR(255)",
        "reset_token_expires":         "ALTER TABLE users ADD COLUMN reset_token_expires TIMESTAMP",
    }
    with engine.begin() as conn:
        for col, sql in new_columns.items():
            if not column_exists(conn, "users", col):
                conn.execute(text(sql))
                print(f"  ✅ Added column: users.{col}")
            else:
                print(f"  ⏭️  Column already exists: users.{col}")


def main():
    print("\n🚀 Quizzie Migration Runner")
    print("=" * 45)

    current = get_current_revision()
    print(f"  Current alembic revision: {current or '(none)'}")

    with engine.connect() as conn:
        users_exists = table_exists(conn, "users")
        proctoring_exists = table_exists(conn, "proctoring_settings")

    print(f"  users table exists:              {users_exists}")
    print(f"  proctoring_settings table exists: {proctoring_exists}")
    print()

    if current is None:
        if users_exists and proctoring_exists:
            # Tables were created by create_all before Alembic was set up.
            # Stamp the DB as being at add_proctoring_001 so Alembic knows
            # those migrations are already applied.
            print("  Tables exist but Alembic has no version stamp.")
            print("  Stamping as 'add_proctoring_001' (tables already exist)...")
            stamp_revision("add_proctoring_001")
            print()

        elif not users_exists:
            # Fresh DB — run all migrations properly via alembic
            print("  Fresh database — running all migrations via alembic...")
            import subprocess
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=os.path.dirname(os.path.abspath(__file__)),
            )
            if result.returncode == 0:
                print("  ✅ All migrations applied.")
            else:
                print("  ❌ Migration failed. Check output above.")
                sys.exit(1)
            return

    # Re-check after possible stamp
    current = get_current_revision()
    print(f"  Revision after stamp: {current}")

    if current == "add_proctoring_001":
        print("\n  Applying email verification migration...")
        apply_email_verification_columns()
        stamp_revision("add_email_verification")

    elif current == "add_email_verification":
        print("  ✅ Already at latest revision. Nothing to do.")

    else:
        # Unknown state — try alembic directly
        print(f"\n  Unknown revision '{current}', attempting alembic upgrade head...")
        import subprocess
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
        )

    print("\n✅ Migration complete! You can now restart the server.\n")


if __name__ == "__main__":
    main()
