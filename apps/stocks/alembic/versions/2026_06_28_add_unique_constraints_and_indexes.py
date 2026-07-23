"""add unique constraints and performance indexes

Revision ID: 2026_06_28_constraints
Revises: 6be1956192ed
Create Date: 2026-06-28 21:26:00.000000

Phase A of Architecture Migration Plan:
- Clean duplicate ai_company_reports (keep newest per ticker)
- Add unique constraint on ai_company_reports.ticker
- Add performance indexes on ai_job_queue and news_articles
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '2026_06_28_constraints'
down_revision: Union[str, Sequence[str], None] = '6be1956192ed'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: Clean duplicates - keep only the newest row per ticker
    op.execute("""
        DELETE FROM ai_company_reports
        WHERE id NOT IN (
            SELECT DISTINCT ON (ticker) id
            FROM ai_company_reports
            ORDER BY ticker, created_at DESC
        )
    """)

    # Step 2: Add unique constraint on ticker
    op.create_unique_constraint(
        'uq_ai_company_reports_ticker',
        'ai_company_reports',
        ['ticker']
    )

    # Step 3: Performance index on news_articles(ticker, pub_date DESC).
    # The historical root migration can initialize a database without the
    # legacy news_articles table, so only apply this legacy-table index when
    # that table is present.
    op.execute("""
        DO $$
        BEGIN
            IF to_regclass('public.news_articles') IS NOT NULL THEN
                CREATE INDEX idx_news_articles_ticker_pubdate
                    ON news_articles (ticker, pub_date);
            END IF;
        END
        $$
    """)

    # Step 4: Index on ai_job_queue for worker polling efficiency
    op.create_index(
        'idx_ai_job_queue_status_scheduled',
        'ai_job_queue',
        ['status', 'scheduled_for'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('idx_ai_job_queue_status_scheduled', table_name='ai_job_queue')
    op.drop_index(
        'idx_news_articles_ticker_pubdate',
        table_name='news_articles',
        if_exists=True,
    )
    op.drop_constraint('uq_ai_company_reports_ticker', 'ai_company_reports', type_='unique')
