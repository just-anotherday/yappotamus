"""raise automated analysis article default and documented ceiling

Revision ID: 2026_08_24_asset_article_50
Revises: 2026_08_14_news_ingestion_state
Create Date: 2026-08-24
"""

from alembic import op
import sqlalchemy as sa


revision = "2026_08_24_asset_article_50"
down_revision = "2026_08_14_news_ingestion_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "assets",
        "max_articles_per_analysis",
        existing_type=sa.Integer(),
        server_default="50",
        comment="Max articles to feed LLM per analysis run (5-50)",
    )


def downgrade() -> None:
    op.alter_column(
        "assets",
        "max_articles_per_analysis",
        existing_type=sa.Integer(),
        server_default="15",
        comment="Max articles to feed LLM per analysis run (5-30)",
    )
