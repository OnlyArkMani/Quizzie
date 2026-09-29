"""attempt integrity: one active attempt, one response per question, server deadline

- responses.client_seq             : ordering guard for out-of-order auto-saves
- responses UNIQUE(attempt_id, question_id) : target of the auto-save upsert
- exam_attempts.deadline           : server-authoritative end time
- exam_attempts.submit_idempotency_key : safe submit retries
- partial UNIQUE INDEX on exam_attempts(exam_id, student_id) WHERE in progress
- cheat_logs(attempt_id, timestamp DESC) for the live feed; drops redundant prefixes

Existing data can already violate the new constraints (that is the bug being
fixed), so the migration first repairs duplicates, then adds the constraints.
Enum literals are written as the enum *names* SQLAlchemy stores
('IN_PROGRESS'); Postgres coerces the literal to the column's enum type.

Revision ID: 006_attempt_integrity
Revises: 005_add_question_types
"""
from alembic import op
import sqlalchemy as sa

revision = '006_attempt_integrity'
down_revision = '005_add_question_types'
branch_labels = None
depends_on = None


def upgrade():
    # 1. New columns (nullable / defaulted, so this is a cheap metadata change).
    #    IF NOT EXISTS: in local dev the app's create_all fallback may already
    #    have created them; the migration must still be able to run.
    op.execute("ALTER TABLE responses ADD COLUMN IF NOT EXISTS client_seq BIGINT NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE exam_attempts ADD COLUMN IF NOT EXISTS deadline TIMESTAMP WITHOUT TIME ZONE")
    op.execute("ALTER TABLE exam_attempts ADD COLUMN IF NOT EXISTS submit_idempotency_key VARCHAR(64)")

    # 2. Repair duplicate responses: keep the most recent answer per question.
    op.execute("""
        DELETE FROM responses r
        USING (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY attempt_id, question_id
                ORDER BY answered_at DESC NULLS LAST, id DESC
            ) AS rn
            FROM responses
        ) d
        WHERE r.id = d.id AND d.rn > 1
    """)

    # 3. Repair duplicate active attempts: keep the newest, close the rest.
    #    (Closed, not deleted — their responses and cheat logs are evidence.)
    op.execute("""
        UPDATE exam_attempts a
        SET status = 'SUBMITTED', submitted_at = COALESCE(a.submitted_at, NOW())
        FROM (
            SELECT id, ROW_NUMBER() OVER (
                PARTITION BY exam_id, student_id ORDER BY started_at DESC, id DESC
            ) AS rn
            FROM exam_attempts
            WHERE status = 'IN_PROGRESS'
        ) d
        WHERE a.id = d.id AND d.rn > 1
    """)

    # 4. Backfill deadlines for attempts still running.
    op.execute("""
        UPDATE exam_attempts a
        SET deadline = a.started_at + make_interval(mins => e.duration_minutes)
        FROM exams e
        WHERE a.exam_id = e.id AND a.status = 'IN_PROGRESS' AND a.deadline IS NULL
    """)

    # 5. Constraints.
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_response_attempt_question') THEN
                ALTER TABLE responses ADD CONSTRAINT uq_response_attempt_question
                    UNIQUE (attempt_id, question_id);
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_one_active_attempt
        ON exam_attempts (exam_id, student_id)
        WHERE status = 'IN_PROGRESS'
    """)

    # 6. Index housekeeping.
    #    (attempt_id, timestamp DESC) serves "latest flag per attempt" in the
    #    examiner live feed (DISTINCT ON) and the violation timeline sort.
    op.execute("CREATE INDEX IF NOT EXISTS idx_cheat_logs_attempt_ts ON cheat_logs (attempt_id, timestamp DESC)")
    #    These single-column indexes are now left-prefixes of wider indexes, so
    #    they only cost write amplification (every auto-save upsert maintains
    #    every index on responses).
    op.execute("DROP INDEX IF EXISTS idx_cheat_logs_attempt_id")
    op.execute("DROP INDEX IF EXISTS idx_responses_attempt_id")


def downgrade():
    op.execute("CREATE INDEX IF NOT EXISTS idx_responses_attempt_id ON responses (attempt_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_cheat_logs_attempt_id ON cheat_logs (attempt_id)")
    op.execute("DROP INDEX IF EXISTS idx_cheat_logs_attempt_ts")
    op.execute("DROP INDEX IF EXISTS uq_one_active_attempt")
    op.drop_constraint('uq_response_attempt_question', 'responses', type_='unique')
    op.drop_column('exam_attempts', 'submit_idempotency_key')
    op.drop_column('exam_attempts', 'deadline')
    op.drop_column('responses', 'client_seq')
