"""users.token_version — server-side token revocation

Revision ID: 007_user_token_version
Revises: 006_attempt_integrity
"""
from alembic import op

revision = '007_user_token_version'
down_revision = '006_attempt_integrity'
branch_labels = None
depends_on = None


def upgrade():
    # Existing tokens carry no "tv" claim and are read as 0, so this deploy
    # doesn't log anyone out.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0")


def downgrade():
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS token_version")
