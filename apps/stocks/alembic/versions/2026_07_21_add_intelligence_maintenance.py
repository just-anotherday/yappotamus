"""add article intelligence maintenance sessions and audit

Revision ID: 2026_07_21_maintenance
Revises: 2026_07_21_intelligence
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "2026_07_21_maintenance"
down_revision = "2026_07_21_intelligence"
branch_labels = None
depends_on = None


def upgrade() -> None:
    json_object = sa.text("'{}'::jsonb")
    json_array = sa.text("'[]'::jsonb")
    op.create_table(
        "article_intelligence_maintenance_batches",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_publish_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("schema_version", sa.String(80), nullable=False),
        sa.Column("state", sa.String(30), server_default="CREATED", nullable=False),
        sa.Column("credential_label", sa.String(80), server_default="maintenance-v1", nullable=False),
        sa.Column("requested_tickers", postgresql.JSONB(), server_default=json_array, nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        *[sa.Column(name, sa.Integer(), server_default="0", nullable=False) for name in (
            "exported_count", "generated_count", "imported_count", "already_exists_count",
            "rejected_count", "hash_mismatch_count", "revision_conflict_count",
        )],
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("registry_revision", sa.String(80), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), server_default=json_object, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_request_id"), sa.UniqueConstraint("client_publish_id"),
    )
    op.create_index("idx_ai_maintenance_batches_state", "article_intelligence_maintenance_batches", ["state", "created_at"])
    op.create_table(
        "article_intelligence_maintenance_export_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=False),
        sa.Column("stable_identity_kind", sa.String(30), nullable=False),
        sa.Column("stable_identity_value", sa.String(512), nullable=False),
        sa.Column("ticker", sa.String(20), nullable=False),
        sa.Column("source_payload", postgresql.JSONB(), nullable=False),
        sa.Column("source_content_hash", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(40), nullable=False),
        sa.Column("prompt_hash", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("revision_hint", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["article_intelligence_maintenance_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["news_articles.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "ordinal", name="uq_ai_maintenance_export_ordinal"),
        sa.UniqueConstraint("batch_id", "article_id", name="uq_ai_maintenance_export_article"),
    )
    op.create_index("idx_ai_maintenance_export_batch", "article_intelligence_maintenance_export_items", ["batch_id", "ordinal"])
    op.create_table(
        "article_intelligence_maintenance_import_items",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("artifact_client_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("client_publish_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("publish_request_hash", sa.String(64), nullable=False),
        sa.Column("is_dry_run", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("article_id", sa.BigInteger(), nullable=True),
        sa.Column("article_intelligence_id", sa.BigInteger(), nullable=True),
        sa.Column("candidate_fingerprint", sa.String(64), nullable=True),
        sa.Column("outcome", sa.String(60), nullable=False),
        sa.Column("reason_code", sa.String(100), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("client_metrics", postgresql.JSONB(), server_default=json_object, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id"], ["article_intelligence_maintenance_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["news_articles.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["article_intelligence_id"], ["article_intelligence.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("batch_id", "artifact_client_id", "is_dry_run", name="uq_ai_maintenance_import_client_item"),
    )
    op.create_index("idx_ai_maintenance_import_fingerprint", "article_intelligence_maintenance_import_items", ["candidate_fingerprint"])
    op.create_index("idx_ai_maintenance_import_batch_outcome", "article_intelligence_maintenance_import_items", ["batch_id", "outcome"])


def downgrade() -> None:
    op.drop_index("idx_ai_maintenance_import_batch_outcome", table_name="article_intelligence_maintenance_import_items")
    op.drop_index("idx_ai_maintenance_import_fingerprint", table_name="article_intelligence_maintenance_import_items")
    op.drop_table("article_intelligence_maintenance_import_items")
    op.drop_index("idx_ai_maintenance_export_batch", table_name="article_intelligence_maintenance_export_items")
    op.drop_table("article_intelligence_maintenance_export_items")
    op.drop_index("idx_ai_maintenance_batches_state", table_name="article_intelligence_maintenance_batches")
    op.drop_table("article_intelligence_maintenance_batches")