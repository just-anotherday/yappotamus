"""add hierarchical article and daily intelligence

Revision ID: 2026_07_21_intelligence
Revises: 2026_07_21_prompt_hash
Create Date: 2026-07-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2026_07_21_intelligence"
down_revision: Union[str, Sequence[str], None] = "2026_07_21_prompt_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_default = sa.text("'{}'::jsonb")
    op.add_column("ai_job_queue", sa.Column("dedupe_key", sa.String(128), nullable=True))
    op.create_index("idx_ai_job_queue_dedupe", "ai_job_queue", ["job_type", "dedupe_key", "status"])
    op.create_table(
        "article_intelligence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_id", sa.BigInteger(), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=True),
        sa.Column("status", sa.String(20), server_default="processing", nullable=False),
        sa.Column("provider", sa.String(40), nullable=True), sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=False), sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("source_content_hash", sa.String(64), nullable=False), sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("generation_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("summary_hash", sa.String(64), nullable=True), sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("sentiment", sa.String(30), nullable=True), sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("importance_score", sa.Integer(), nullable=True), sa.Column("market_impact", sa.Text(), nullable=True),
        sa.Column("short_term_outlook", sa.Text(), nullable=True), sa.Column("long_term_outlook", sa.Text(), nullable=True),
        sa.Column("structured_data", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("routing_metadata", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("evaluation_metadata", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=True), sa.Column("generation_duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True), sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('processing','completed','failed')", name="ck_article_intelligence_status"),
        sa.CheckConstraint("generation_revision > 0", name="ck_article_intelligence_generation_revision"),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 1 AND 10", name="ck_article_intelligence_confidence"),
        sa.CheckConstraint("importance_score IS NULL OR importance_score BETWEEN 1 AND 10", name="ck_article_intelligence_importance"),
        sa.ForeignKeyConstraint(["article_id"], ["news_articles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("article_id", "source_content_hash", "prompt_hash", "input_hash", "generation_revision", name="uq_article_intelligence_generation"),
    )
    op.create_index("idx_article_intelligence_article_created", "article_intelligence", ["article_id", "created_at"])
    op.create_index("idx_article_intelligence_ticker_status", "article_intelligence", ["ticker", "status"])
    op.create_index("idx_article_intelligence_source_hash", "article_intelligence", ["source_content_hash"])

    op.create_table(
        "daily_ticker_intelligence",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False), sa.Column("asset_id", sa.BigInteger(), nullable=True),
        sa.Column("ticker", sa.String(20), nullable=False), sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False), sa.Column("status", sa.String(20), server_default="processing", nullable=False),
        sa.Column("provider", sa.String(40), nullable=True), sa.Column("model", sa.String(100), nullable=True),
        sa.Column("prompt_version", sa.String(40), nullable=False), sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("source_set_hash", sa.String(64), nullable=False), sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("summary_hash", sa.String(64), nullable=True), sa.Column("input_article_count", sa.Integer(), nullable=False),
        sa.Column("overall_sentiment", sa.String(30), nullable=True), sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("executive_summary", sa.Text(), nullable=True),
        sa.Column("structured_data", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("routing_metadata", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("evaluation_metadata", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=True), sa.Column("generation_duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True), sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("revision > 0", name="ck_daily_ticker_intelligence_revision"),
        sa.CheckConstraint("input_article_count > 0", name="ck_daily_ticker_intelligence_nonempty"),
        sa.CheckConstraint("confidence IS NULL OR confidence BETWEEN 1 AND 10", name="ck_daily_ticker_intelligence_confidence"),
        sa.CheckConstraint("status IN ('processing','completed','failed')", name="ck_daily_ticker_intelligence_status"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="SET NULL"), sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ticker", "trading_date", "revision", name="uq_daily_ticker_intelligence_revision"),
        sa.UniqueConstraint("ticker", "trading_date", "source_set_hash", "prompt_hash", name="uq_daily_ticker_intelligence_generation"),
    )
    op.create_index("idx_daily_ticker_intelligence_current", "daily_ticker_intelligence", ["ticker", "trading_date", "revision"])
    op.create_index("idx_daily_ticker_intelligence_status", "daily_ticker_intelligence", ["status"])

    op.create_table(
        "daily_ticker_intelligence_sources",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("daily_intelligence_id", sa.BigInteger(), nullable=False), sa.Column("article_intelligence_id", sa.BigInteger(), nullable=False),
        sa.Column("source_rank", sa.Integer(), nullable=False), sa.Column("importance_score_used", sa.Integer(), nullable=False),
        sa.Column("is_top_article", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("source_rank > 0", name="ck_daily_intelligence_source_rank"),
        sa.CheckConstraint("importance_score_used BETWEEN 1 AND 10", name="ck_daily_intelligence_source_importance"),
        sa.ForeignKeyConstraint(["daily_intelligence_id"], ["daily_ticker_intelligence.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_intelligence_id"], ["article_intelligence.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("daily_intelligence_id", "article_intelligence_id", name="uq_daily_intelligence_source"),
        sa.UniqueConstraint("daily_intelligence_id", "source_rank", name="uq_daily_intelligence_source_rank"),
    )
    op.create_index("idx_daily_intelligence_sources_article", "daily_ticker_intelligence_sources", ["article_intelligence_id"])

    op.create_table(
        "ai_generation_evaluations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("artifact_type", sa.String(40), nullable=False), sa.Column("artifact_identity", sa.String(128), nullable=False),
        sa.Column("artifact_id", sa.BigInteger(), nullable=True), sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=False), sa.Column("model", sa.String(100), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False), sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("routing_metadata", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("validation_metadata", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("metrics", postgresql.JSONB(), server_default=json_default, nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False), sa.Column("fallback_index", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True), sa.Column("generated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("artifact_type", "artifact_identity", "attempt_number", name="uq_ai_generation_evaluation_attempt"),
    )
    op.create_index("idx_ai_generation_evaluations_provider_model", "ai_generation_evaluations", ["provider", "model"])
    op.create_index("idx_ai_generation_evaluations_artifact", "ai_generation_evaluations", ["artifact_type", "artifact_id"])


def downgrade() -> None:
    op.drop_table("ai_generation_evaluations")
    op.drop_table("daily_ticker_intelligence_sources")
    op.drop_table("daily_ticker_intelligence")
    op.drop_table("article_intelligence")
    op.drop_index("idx_ai_job_queue_dedupe", table_name="ai_job_queue")
    op.drop_column("ai_job_queue", "dedupe_key")