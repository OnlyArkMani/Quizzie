"""add email verification and password reset fields

Revision ID: add_email_verification
Revises: 
Create Date: 2024-01-01

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_email_verification'
down_revision = 'add_proctoring_001'  # chains after the proctoring migration
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('is_verified',                   sa.Boolean(),  nullable=False, server_default='false'))
    op.add_column('users', sa.Column('verification_token',            sa.String(255), nullable=True))
    op.add_column('users', sa.Column('verification_token_expires',    sa.DateTime(),  nullable=True))
    op.add_column('users', sa.Column('reset_token',                   sa.String(255), nullable=True))
    op.add_column('users', sa.Column('reset_token_expires',           sa.DateTime(),  nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'reset_token_expires')
    op.drop_column('users', 'reset_token')
    op.drop_column('users', 'verification_token_expires')
    op.drop_column('users', 'verification_token')
    op.drop_column('users', 'is_verified')
