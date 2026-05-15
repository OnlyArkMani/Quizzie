"""add performance indexes for 500 concurrent students

Revision ID: 003_add_performance_indexes
Revises: add_email_verification
Create Date: 2025-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = '003_add_performance_indexes'
down_revision = 'add_email_verification'
branch_labels = None
depends_on = None


def upgrade():
    # exam_attempts — most-queried table (start, submit, results, monitoring)
    op.create_index('idx_attempts_student_id',  'exam_attempts', ['student_id'])
    op.create_index('idx_attempts_exam_id',     'exam_attempts', ['exam_id'])
    op.create_index('idx_attempts_status',      'exam_attempts', ['status'])
    op.create_index('idx_attempts_exam_student','exam_attempts', ['exam_id', 'student_id'])

    # responses — queried on every evaluation + analytics
    op.create_index('idx_responses_attempt_id',  'responses', ['attempt_id'])
    op.create_index('idx_responses_question_id', 'responses', ['question_id'])

    # cheat_logs — queried per attempt by monitoring endpoints
    op.create_index('idx_cheat_logs_attempt_id', 'cheat_logs', ['attempt_id'])

    # questions — fetched per exam (already cached but index needed for cache miss)
    op.create_index('idx_questions_exam_id', 'questions', ['exam_id'])
    op.create_index('idx_questions_display_order', 'questions', ['exam_id', 'display_order'])

    # exams — filtered by status + creator
    op.create_index('idx_exams_status',      'exams', ['status'])
    op.create_index('idx_exams_created_by',  'exams', ['created_by'])


def downgrade():
    op.drop_index('idx_attempts_student_id',   'exam_attempts')
    op.drop_index('idx_attempts_exam_id',      'exam_attempts')
    op.drop_index('idx_attempts_status',       'exam_attempts')
    op.drop_index('idx_attempts_exam_student', 'exam_attempts')
    op.drop_index('idx_responses_attempt_id',  'responses')
    op.drop_index('idx_responses_question_id', 'responses')
    op.drop_index('idx_cheat_logs_attempt_id', 'cheat_logs')
    op.drop_index('idx_questions_exam_id',         'questions')
    op.drop_index('idx_questions_display_order',   'questions')
    op.drop_index('idx_exams_status',     'exams')
    op.drop_index('idx_exams_created_by', 'exams')
