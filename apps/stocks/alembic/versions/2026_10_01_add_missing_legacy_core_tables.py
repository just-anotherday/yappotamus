"""add legacy core tables required by a fresh installation

Revision ID: 2026_10_01_legacy_core_tables
Revises: 2026_08_24_asset_article_50
Create Date: 2026-10-01

The original database predated Alembic and already contained these tables.
Fresh databases therefore reached Alembic head without the tables used by the
watchlist, legacy reports, and intraday price services. Existing compatible
tables are preserved.
"""

from alembic import op


revision = "2026_10_01_legacy_core_tables"
down_revision = "2026_08_24_asset_article_50"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS watchlist (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL UNIQUE,
            position INTEGER NOT NULL DEFAULT 0,
            added_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_reports (
            id BIGSERIAL PRIMARY KEY,
            ticker TEXT NOT NULL,
            report_data JSONB NOT NULL,
            overall_sentiment VARCHAR(20) NOT NULL,
            confidence_score INTEGER NOT NULL,
            articles_count INTEGER NOT NULL,
            model_used VARCHAR(50) NOT NULL DEFAULT '',
            prompt_version VARCHAR(20) NOT NULL DEFAULT '1.0',
            prompt_hash VARCHAR(64),
            current_price_at_analysis DOUBLE PRECISION,
            created_at TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_ticker ON analysis_reports (ticker)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_created ON analysis_reports (created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_ticker_created "
        "ON analysis_reports (ticker, created_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS intraday_ohlcv (
            id SERIAL PRIMARY KEY,
            ticker VARCHAR(10) NOT NULL,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            open_price DOUBLE PRECISION,
            high DOUBLE PRECISION,
            low DOUBLE PRECISION,
            close DOUBLE PRECISION,
            volume BIGINT
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_intraday_ticker_timestamp "
        "ON intraday_ohlcv (ticker, timestamp)"
    )

    op.execute(
        """
        DO $validation$
        DECLARE
            missing TEXT;
        BEGIN
            WITH expected(table_name, column_name) AS (
                VALUES
                    ('watchlist', 'id'),
                    ('watchlist', 'ticker'),
                    ('watchlist', 'position'),
                    ('watchlist', 'added_at'),
                    ('analysis_reports', 'id'),
                    ('analysis_reports', 'ticker'),
                    ('analysis_reports', 'report_data'),
                    ('analysis_reports', 'overall_sentiment'),
                    ('analysis_reports', 'confidence_score'),
                    ('analysis_reports', 'articles_count'),
                    ('analysis_reports', 'model_used'),
                    ('analysis_reports', 'prompt_version'),
                    ('analysis_reports', 'prompt_hash'),
                    ('analysis_reports', 'current_price_at_analysis'),
                    ('analysis_reports', 'created_at'),
                    ('intraday_ohlcv', 'id'),
                    ('intraday_ohlcv', 'ticker'),
                    ('intraday_ohlcv', 'timestamp'),
                    ('intraday_ohlcv', 'open_price'),
                    ('intraday_ohlcv', 'high'),
                    ('intraday_ohlcv', 'low'),
                    ('intraday_ohlcv', 'close'),
                    ('intraday_ohlcv', 'volume')
            )
            SELECT string_agg(expected.table_name || '.' || expected.column_name, ', ')
              INTO missing
              FROM expected
              LEFT JOIN information_schema.columns actual
                ON actual.table_schema = 'public'
               AND actual.table_name = expected.table_name
               AND actual.column_name = expected.column_name
             WHERE actual.column_name IS NULL;

            IF missing IS NOT NULL THEN
                RAISE EXCEPTION 'Legacy core table migration is missing required columns: %', missing;
            END IF;
        END
        $validation$;
        """
    )


def downgrade() -> None:
    # These tables predate Alembic on existing installations. Dropping them on
    # downgrade could destroy user data, so the safe downgrade is intentionally
    # a no-op.
    pass
