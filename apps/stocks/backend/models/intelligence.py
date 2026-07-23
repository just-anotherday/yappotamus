"""Append-only Article and Daily Intelligence persistence models."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer,
    String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.config.database import Base


class ArticleIntelligence(Base):
    __tablename__ = "article_intelligence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("news_articles.id", ondelete="RESTRICT"), nullable=False)
    asset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    ticker: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="processing")
    provider: Mapped[Optional[str]] = mapped_column(String(40))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    generation_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    summary_hash: Mapped[Optional[str]] = mapped_column(String(64))
    summary: Mapped[Optional[str]] = mapped_column(Text)
    sentiment: Mapped[Optional[str]] = mapped_column(String(30))
    confidence: Mapped[Optional[int]] = mapped_column(Integer)
    importance_score: Mapped[Optional[int]] = mapped_column(Integer)
    market_impact: Mapped[Optional[str]] = mapped_column(Text)
    short_term_outlook: Mapped[Optional[str]] = mapped_column(Text)
    long_term_outlook: Mapped[Optional[str]] = mapped_column(Text)
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    routing_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    evaluation_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    generation_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_code: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("article_id", "source_content_hash", "prompt_hash", "input_hash", "generation_revision", name="uq_article_intelligence_generation"),
        CheckConstraint("generation_revision > 0", name="ck_article_intelligence_generation_revision"),
        CheckConstraint("status IN ('processing','completed','failed')", name="ck_article_intelligence_status"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 1 AND 10", name="ck_article_intelligence_confidence"),
        CheckConstraint("importance_score IS NULL OR importance_score BETWEEN 1 AND 10", name="ck_article_intelligence_importance"),
        Index("idx_article_intelligence_article_created", "article_id", "created_at"),
        Index("idx_article_intelligence_ticker_status", "ticker", "status"),
        Index("idx_article_intelligence_source_hash", "source_content_hash"),
    )


class DailyTickerIntelligence(Base):
    __tablename__ = "daily_ticker_intelligence"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("assets.id", ondelete="SET NULL"))
    ticker: Mapped[str] = mapped_column(String(20), nullable=False)
    trading_date: Mapped[date] = mapped_column(Date, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="processing")
    provider: Mapped[Optional[str]] = mapped_column(String(40))
    model: Mapped[Optional[str]] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    summary_hash: Mapped[Optional[str]] = mapped_column(String(64))
    input_article_count: Mapped[int] = mapped_column(Integer, nullable=False)
    overall_sentiment: Mapped[Optional[str]] = mapped_column(String(30))
    confidence: Mapped[Optional[int]] = mapped_column(Integer)
    executive_summary: Mapped[Optional[str]] = mapped_column(Text)
    structured_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    routing_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    evaluation_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime)
    generation_duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    error_code: Mapped[Optional[str]] = mapped_column(String(100))
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("ticker", "trading_date", "revision", name="uq_daily_ticker_intelligence_revision"),
        UniqueConstraint("ticker", "trading_date", "source_set_hash", "prompt_hash", name="uq_daily_ticker_intelligence_generation"),
        CheckConstraint("revision > 0", name="ck_daily_ticker_intelligence_revision"),
        CheckConstraint("input_article_count > 0", name="ck_daily_ticker_intelligence_nonempty"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 1 AND 10", name="ck_daily_ticker_intelligence_confidence"),
        CheckConstraint("status IN ('processing','completed','failed')", name="ck_daily_ticker_intelligence_status"),
        Index("idx_daily_ticker_intelligence_current", "ticker", "trading_date", "revision"),
        Index("idx_daily_ticker_intelligence_status", "status"),
    )


class DailyTickerIntelligenceSource(Base):
    __tablename__ = "daily_ticker_intelligence_sources"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    daily_intelligence_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("daily_ticker_intelligence.id", ondelete="CASCADE"), nullable=False)
    article_intelligence_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("article_intelligence.id", ondelete="RESTRICT"), nullable=False)
    source_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    importance_score_used: Mapped[int] = mapped_column(Integer, nullable=False)
    is_top_article: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("daily_intelligence_id", "article_intelligence_id", name="uq_daily_intelligence_source"),
        UniqueConstraint("daily_intelligence_id", "source_rank", name="uq_daily_intelligence_source_rank"),
        CheckConstraint("source_rank > 0", name="ck_daily_intelligence_source_rank"),
        CheckConstraint("importance_score_used BETWEEN 1 AND 10", name="ck_daily_intelligence_source_importance"),
        Index("idx_daily_intelligence_sources_article", "article_intelligence_id"),
    )


class AIGenerationEvaluation(Base):
    __tablename__ = "ai_generation_evaluations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    artifact_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    artifact_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    prompt_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    routing_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    validation_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    succeeded: Mapped[bool] = mapped_column(nullable=False)
    fallback_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("artifact_type", "artifact_identity", "attempt_number", name="uq_ai_generation_evaluation_attempt"),
        Index("idx_ai_generation_evaluations_provider_model", "provider", "model"),
        Index("idx_ai_generation_evaluations_artifact", "artifact_type", "artifact_id"),
    )