"""Add proctoring settings and health tracking

Revision ID: add_proctoring_001
Revises: 
Create Date: 2024-02-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'add_proctoring_001'
down_revision = None  # Change this to your last migration ID if you have previous migrations
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create proctoring_settings table
    op.create_table(
        'proctoring_settings',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('exam_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('camera_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('microphone_enabled', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('face_detection_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('multiple_face_detection', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('head_pose_detection', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('tab_switch_detection', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('min_face_confidence', sa.Numeric(precision=3, scale=2), nullable=False, server_default='0.6'),
        sa.Column('max_head_rotation', sa.Numeric(precision=5, scale=2), nullable=False, server_default='30.0'),
        sa.Column('detection_interval', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('initial_health', sa.Integer(), nullable=False, server_default='100'),
        sa.Column('health_warning_threshold', sa.Integer(), nullable=False, server_default='40'),
        sa.Column('auto_submit_on_zero_health', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), onupdate=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['exam_id'], ['exams.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('exam_id', name='uq_proctoring_settings_exam_id')
    )
    
    # Create index for faster lookups
    op.create_index('ix_proctoring_settings_exam_id', 'proctoring_settings', ['exam_id'])
    
    # Add current_health column to exam_attempts table
    op.add_column('exam_attempts', 
        sa.Column('current_health', sa.Integer(), nullable=True, server_default='100')
    )
    
    # Add index on current_health for filtering
    op.create_index('ix_exam_attempts_current_health', 'exam_attempts', ['current_health'])
    
    # Add metadata column to cheat_logs if not exists (for storing additional violation data)
    # This is using JSONB which is more efficient for querying
    try:
        op.add_column('cheat_logs',
            sa.Column('metadata', postgresql.JSONB(), nullable=True)
        )
    except:
        # Column might already exist
        pass


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_exam_attempts_current_health', table_name='exam_attempts')
    
    # Remove current_health column
    op.drop_column('exam_attempts', 'current_health')
    
    # Remove index
    op.drop_index('ix_proctoring_settings_exam_id', table_name='proctoring_settings')
    
    # Drop proctoring_settings table
    op.drop_table('proctoring_settings')
    
    # Note: We don't drop the metadata column from cheat_logs as it might have been there before