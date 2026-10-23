"""Restrict Stocks tables to the trusted backend database connection.

The browser uses Supabase only for Auth. It must never access these tables
through the Data API, even with a valid non-owner Supabase session.
"""
from alembic import op

revision = "2026_10_23_private_app_tables"
down_revision = "2026_10_01_legacy_core_tables"
branch_labels = None
depends_on = None

# Explicit scope: do not change unrelated applications or Supabase Auth tables.
PRIVATE_TABLES = (
    "news_articles", "watchlist", "analysis_reports", "assets", "asset_tickers",
    "ai_job_queue", "ai_company_reports", "ai_sector_reports", "ai_market_reports",
    "ai_company_report_history", "article_intelligence", "daily_ticker_intelligence",
    "daily_ticker_intelligence_sources", "ai_generation_evaluations",
    "article_intelligence_maintenance_batches",
    "article_intelligence_maintenance_export_items",
    "article_intelligence_maintenance_import_items", "news_ingestion_state",
    "daily_ohlcv", "market_tracker_info", "intraday_ohlcv",
)


def upgrade() -> None:
    tables = ", ".join("'" + name + "'" for name in PRIVATE_TABLES)
    op.execute(f"""
    DO $private_tables$
    DECLARE
        table_name text;
        role_name text;
    BEGIN
        FOREACH table_name IN ARRAY ARRAY[{tables}] LOOP
            IF to_regclass(format('public.%I', table_name)) IS NOT NULL THEN
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', table_name);
                EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC', table_name);
                FOR role_name IN SELECT rolname FROM pg_roles
                    WHERE rolname IN ('anon', 'authenticated') LOOP
                    EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE public.%I FROM %I', table_name, role_name);
                END LOOP;
            END IF;
        END LOOP;
    END
    $private_tables$;
    """)


def downgrade() -> None:
    # Automatically restoring blanket grants would reopen private reports.
    raise RuntimeError("Security migration requires a separately reviewed permission rollback")
