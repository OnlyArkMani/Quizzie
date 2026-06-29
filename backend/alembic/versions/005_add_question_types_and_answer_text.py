"""add coding/subjective question types and free-text answers

- Extends the questiontype enum with 'coding' and 'subjective'.
- Adds questions.reference_answer (model answer / rubric) and questions.language.
- Adds responses.answer_text for free-text/code answers.
- Makes responses.selected_option_ids nullable (manual types have no options).

Revision ID: 005_add_question_types
Revises: 004_add_attempt_current_health
Create Date: 2026-06-28 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '005_add_question_types'
down_revision = '004_add_attempt_current_health'
branch_labels = None
depends_on = None


def upgrade():
    # New enum values must be added outside a transaction block on PostgreSQL.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE questiontype ADD VALUE IF NOT EXISTS 'coding'")
        op.execute("ALTER TYPE questiontype ADD VALUE IF NOT EXISTS 'subjective'")

    op.add_column('questions', sa.Column('reference_answer', sa.Text(), nullable=True))
    op.add_column('questions', sa.Column('language', sa.String(length=50), nullable=True))

    op.add_column('responses', sa.Column('answer_text', sa.Text(), nullable=True))
    op.alter_column('responses', 'selected_option_ids', existing_type=postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=True)


def downgrade():
    op.alter_column('responses', 'selected_option_ids', existing_type=postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False)
    op.drop_column('responses', 'answer_text')
    op.drop_column('questions', 'language')
    op.drop_column('questions', 'reference_answer')
    # NOTE: PostgreSQL cannot drop individual enum values, so 'coding' and
    # 'subjective' remain on the questiontype enum after a downgrade. Harmless.
