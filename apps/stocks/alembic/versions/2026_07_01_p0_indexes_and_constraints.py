"""add p0 performance indexes and unique constraints

Revision ID: 2026_07_01_p0_indexes_and_constraints
Revises: 2026_07_01_add_price_history_and_market_trackers
Create Date: 2026-07-01 17:40:00.000000

P0 Critical Database Optimizations from VERIFICATION_REPORT.md:
- Partial dispatch index on ai_job_queue for worker polling (status + priority + scheduled_for)
- Compound index on ai_company_reports(asset_id, updated_at DESC) for latest-report lookups
- Unique constraint on ai_sector_reports.sector
- Unique constraint on ai_market_reports.report_date
"""
from typing import Sequence, Union

from alembic import op


revision: str = "2026_07_01_p0_indexes_and_constraints"
down_revision: Union[str, None] = "2026_07_01_add_price_history_and_market_trackers"
branch_labels: Union[tuple, None] = None
depends_on: Union[tuple, None] = None


def upgrade() -> None:
    # 1. Partial dispatch index on ai_job_queue — only indexes active rows (pending/processing)
    #    ordered by priority ASC then scheduled_for ASC for optimal polling
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_job_dispatch
        ON ai_job_queue (status, priority ASC, scheduled_for ASC)
        WHERE status IN ('pending', 'processing')
    """)

    # 2. Compound index on ai_company_reports(asset_id, updated_at DESC)
    #    Used by market report handler to find latest report per asset efficiently
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_ai_company_asset_updated
        ON ai_company_reports (asset_id, updated_at DESC)
    """)

    # 3. Unique constraint on ai_sector_reports.sector
    #    One sector report at a time; upserts in ai_worker handle updates
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_ai_sector_reports_sector'
            ) THEN
                ALTER TABLE ai_sector_reports ADD CONSTRAINT uq_ai_sector_reports_sector UNIQUE (sector);
            END IF;
        END $$;
    """)

    # 4. Unique constraint on ai_market_reports.report_date
    #    One market report per calendar day
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'uq_ai_market_reports_report_date'
            ) THEN
                ALTER TABLE ai_market_reports ADD CONSTRAINT uq_ai_market_reports_report_date UNIQUE (report_date);
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE ai_market_reports DROP CONSTRAINT IF EXISTS uq_ai_market_reports_report_date")
    op.execute("ALTER TABLE ai_sector_reports DROP CONSTRAINT IF EXISTS uq_ai_sector_reports_sector")
    op.execute("DROP INDEX IF EXISTS idx_ai_company_asset_updated")
    op.execute("DROP INDEX IF EXISTS idx_ai_job_dispatch")
