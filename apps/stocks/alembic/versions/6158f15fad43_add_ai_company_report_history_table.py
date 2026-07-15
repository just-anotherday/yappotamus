"""add ai_company_report_history table

Revision ID: 6158f15fad43
Revises: 2026_07_01_p0_indexes_and_constraints
Create Date: 2026-07-04 09:08:40.544688
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '6158f15fad43'
down_revision: Union[str, Sequence[str], None] = '2026_07_01_p0_indexes_and_constraints'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the history table for AI company report audit trail
    op.create_table(
        'ai_company_report_history',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('original_report_id', sa.BigInteger(), nullable=True),
        sa.Column('ticker', sa.String(length=20), nullable=False),
        sa.Column('overall_sentiment', sa.String(length=20), nullable=False),
        sa.Column('confidence_score', sa.Integer(), nullable=False),
        sa.Column('articles_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('model_used', sa.String(length=50), server_default='', nullable=False),
        sa.Column('prompt_version', sa.String(length=20), server_default='1.0', nullable=False),
        sa.Column('price_snapshot', postgresql.DOUBLE_PRECISION(precision=53), nullable=True),
        sa.Column('report_data_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', postgresql.TIMESTAMP(), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('ai_company_report_history_pkey')),
    )
    # FK to ai_company_reports (set NULL if original report deleted)
    op.create_foreign_key(
        op.f('ai_company_report_history_original_report_id_ai_company_reports_fkey'),
        'ai_company_report_history', 'ai_company_reports',
        ['original_report_id'], ['id'],
        ondelete='SET NULL',
    )
    # Indexes for fast lookups
    op.create_index('idx_report_history_ticker_created', 'ai_company_report_history', ['ticker', 'created_at'])
    op.create_index('idx_report_history_ticker_sentiment', 'ai_company_report_history', ['ticker', 'overall_sentiment'])
    op.create_index(op.f('ix_ai_company_report_history_original_report_id'), 'ai_company_report_history', ['original_report_id'])
    op.create_index(op.f('ix_ai_company_report_history_ticker'), 'ai_company_report_history', ['ticker'])


def downgrade() -> None:
    op.drop_index(op.f('ix_ai_company_report_history_ticker'), table_name='ai_company_report_history')
    op.drop_index(op.f('ix_ai_company_report_history_original_report_id'), table_name='ai_company_report_history')
    op.drop_index('idx_report_history_ticker_sentiment', table_name='ai_company_report_history')
    op.drop_index('idx_report_history_ticker_created', table_name='ai_company_report_history')
    op.drop_constraint(
        op.f('ai_company_report_history_original_report_id_ai_company_reports_fkey'),
        'ai_company_report_history', type_='foreignkey'
    )
    op.drop_table('ai_company_report_history')
