"""Add per-asset analysis configuration columns

Revision ID: 2026_06_28_add_asset_analysis_config
Revises: 2026_06_28_add_unique_constraints_and_indexes
Create Date: 2026-06-28 22:25:00

Adds two configurable columns to the assets table so the automated AI worker
can use per-ticker settings instead of hardcoded values:
  - analysis_window_days: how far back to search for articles (default 7)
  - max_articles_per_analysis: max articles fed to LLM per run (default 15)
"""

from alembic import op
import sqlalchemy as sa


revision = "2026_06_28_add_asset_analysis_config"
down_revision = "2026_06_28_constraints"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "assets",
        sa.Column(
            "analysis_window_days",
            sa.Integer(),
            server_default="7",
            nullable=True,  # allow NULL during migration; backfill below
            comment="Days back to look for articles in automated reports (1-90)",
        ),
    )
    op.add_column(
        "assets",
        sa.Column(
            "max_articles_per_analysis",
            sa.Integer(),
            server_default="15",
            nullable=True,
            comment="Max articles to feed LLM per analysis run (5-30)",
        ),
    )

    # Backfill: set defaults for existing rows that might be NULL
    op.execute("""
        UPDATE assets
        SET
            analysis_window_days = COALESCE(analysis_window_days, 7),
            max_articles_per_analysis = COALESCE(max_articles_per_analysis, 15)
        WHERE analysis_window_days IS NULL OR max_articles_per_analysis IS NULL
    """)

    # Make columns NOT NULL after backfill
    op.alter_column("assets", "analysis_window_days", nullable=False)
    op.alter_column("assets", "max_articles_per_analysis", nullable=False)


def downgrade():
    op.drop_column("assets", "max_articles_per_analysis")
    op.drop_column("assets", "analysis_window_days")
