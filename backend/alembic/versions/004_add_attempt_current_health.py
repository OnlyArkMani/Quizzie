"""add current_health column to exam_attempts

Persists proctoring health so it no longer has to be recomputed by replaying the
full cheat_log history on every request, and so health recovery actually sticks.
Backfills existing in-progress attempts by replaying their logs once.

Revision ID: 004_add_attempt_current_health
Revises: 003_add_performance_indexes
Create Date: 2026-06-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '004_add_attempt_current_health'
down_revision = '003_add_performance_indexes'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('exam_attempts', sa.Column('current_health', sa.Integer(), nullable=True))

    # Best-effort backfill for attempts still in progress. New/NULL rows are
    # lazily initialised by the API, so this only needs to handle live exams.
    bind = op.get_bind()
    try:
        from app.ai_monitor import scoring

        attempts = bind.execute(sa.text(
            "SELECT a.id, COALESCE(p.initial_health, 100) AS init "
            "FROM exam_attempts a "
            "LEFT JOIN proctoring_settings p ON p.exam_id = a.exam_id "
            "WHERE a.status = 'in_progress'"
        )).fetchall()

        for attempt_id, init in attempts:
            logs = bind.execute(sa.text(
                "SELECT flag_type, severity FROM cheat_logs WHERE attempt_id = :aid"
            ), {"aid": attempt_id}).fetchall()
            health = int(init)
            for flag_type, severity in logs:
                health = max(0, health - scoring.health_penalty(flag_type, severity))
            bind.execute(sa.text(
                "UPDATE exam_attempts SET current_health = :h WHERE id = :aid"
            ), {"h": health, "aid": attempt_id})
    except Exception:
        # Backfill is non-critical; lazy init covers any rows left NULL.
        pass


def downgrade():
    op.drop_column('exam_attempts', 'current_health')
