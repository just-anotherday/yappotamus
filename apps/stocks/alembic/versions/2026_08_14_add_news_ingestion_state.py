"""add durable news ingestion lease and health state

Revision ID: 2026_08_14_news_ingestion_state
Revises: 2026_07_27_ai_job_leases
Create Date: 2026-08-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2026_08_14_news_ingestion_state"
down_revision: Union[str, None] = "2026_07_27_ai_job_leases"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_ingestion_state",
        sa.Column("job_name", sa.String(length=64), nullable=False),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_successful_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_article_retrieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_article_inserted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_retrieved_pub_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("latest_inserted_pub_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_status", sa.String(length=32), nullable=True),
        sa.Column("last_error_code", sa.String(length=64), nullable=True),
        sa.Column(
            "last_metrics",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("consecutive_failures >= 0", name="ck_news_ingestion_failures_nonnegative"),
        sa.PrimaryKeyConstraint("job_name"),
    )
    op.create_index(
        "idx_news_ingestion_state_lease_expires",
        "news_ingestion_state",
        ["lease_expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("idx_news_ingestion_state_lease_expires", table_name="news_ingestion_state")
    op.drop_table("news_ingestion_state")
