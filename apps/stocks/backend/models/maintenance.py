"""Persistence for resumable Article Intelligence maintenance sessions."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.config.database import Base


class ArticleIntelligenceMaintenanceBatch(Base):
    __tablename__ = "article_intelligence_maintenance_batches"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    client_request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    client_publish_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), unique=True)
    schema_version: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, server_default="CREATED")
    credential_label: Mapped[str] = mapped_column(String(80), nullable=False, server_default="maintenance-v1")
    requested_tickers: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    requested_count: Mapped[int] = mapped_column(Integer, nullable=False)
    exported_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    generated_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    imported_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    already_exists_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    hash_mismatch_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    revision_conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    registry_revision: Mapped[str] = mapped_column(String(80), nullable=False)
    model: Mapped[str | None] = mapped_column(String(100))
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("idx_ai_maintenance_batches_state", "state", "created_at"),)


class ArticleIntelligenceMaintenanceExportItem(Base):
    __tablename__ = "article_intelligence_maintenance_export_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_intelligence_maintenance_batches.id", ondelete="CASCADE"), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("news_articles.id", ondelete="RESTRICT"), nullable=False)
    stable_identity_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    stable_identity_value: Mapped[str] = mapped_column(String(512), nullable=False)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    source_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision_hint: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("batch_id", "ordinal", name="uq_ai_maintenance_export_ordinal"),
        UniqueConstraint("batch_id", "article_id", name="uq_ai_maintenance_export_article"),
        Index("idx_ai_maintenance_export_batch", "batch_id", "ordinal"),
    )


class ArticleIntelligenceMaintenanceImportItem(Base):
    __tablename__ = "article_intelligence_maintenance_import_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), ForeignKey("article_intelligence_maintenance_batches.id", ondelete="CASCADE"), nullable=False)
    artifact_client_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    client_publish_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    publish_request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    is_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    article_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("news_articles.id", ondelete="RESTRICT"))
    article_intelligence_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("article_intelligence.id", ondelete="RESTRICT"))
    candidate_fingerprint: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[str] = mapped_column(String(60), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(100))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    client_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("batch_id", "artifact_client_id", "is_dry_run", name="uq_ai_maintenance_import_client_item"),
        Index("idx_ai_maintenance_import_fingerprint", "candidate_fingerprint"),
        Index("idx_ai_maintenance_import_batch_outcome", "batch_id", "outcome"),
    )