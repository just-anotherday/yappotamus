"""add price history and market tracker tables

Revision ID: 2026_07_01_add_price_history_and_market_trackers
Revises: 2026_06_28_add_asset_analysis_config
Create Date: 2026-07-01 09:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2026_07_01_add_price_history_and_market_trackers"
down_revision: Union[str, None] = "2026_06_28_add_asset_analysis_config"
branch_labels: Union[tuple, None] = None
depends_on: Union[tuple, None] = None


def upgrade() -> None:
    # Use raw SQL with IF NOT EXISTS so PG doesn't abort the transaction
    op.execute("""
        CREATE TABLE IF NOT EXISTS daily_ohlcv (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            date DATE NOT NULL,
            open_price FLOAT,
            high FLOAT,
            low FLOAT,
            close FLOAT,
            volume BIGINT,
            adjusted_close FLOAT,
            CONSTRAINT uq_ticker_date UNIQUE (ticker, date)
        )
    """)

    op.execute("CREATE INDEX IF NOT EXISTS ix_daily_ohlcv_ticker ON daily_ohlcv (ticker)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_daily_ohlcv_date ON daily_ohlcv (date)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS market_tracker_info (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL UNIQUE,
            display_name VARCHAR(100) NOT NULL,
            description VARCHAR(500),
            coverage_scope VARCHAR(200),
            what_it_measures VARCHAR(500),
            top_sectors VARCHAR(1000),
            key_constituents VARCHAR(2000),
            active INTEGER DEFAULT 1
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS market_tracker_info")
    op.execute("DROP TABLE IF EXISTS daily_ohlcv")
