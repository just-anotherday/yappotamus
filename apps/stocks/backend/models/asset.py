"""
Asset ORM Model — Canonical entity for Companies, Stocks, ETFs, Crypto, Indexes, Commodities.

Every financial asset is represented as a first-class entity. Tickers become attributes
of assets rather than primary identifiers, enabling:
- Multi-symbol history (IPO changes, delistings)
- Cross-asset-class support
- Proper relational modeling for AI reports and intelligence

Table:
    assets (
        id BIGSERIAL PRIMARY KEY,
        slug VARCHAR(100) UNIQUE NOT NULL,
        name TEXT NOT NULL,
        asset_type VARCHAR(20) NOT NULL DEFAULT 'stock',
        sector VARCHAR(100),
        industry VARCHAR(100),
        exchange VARCHAR(20),
        country VARCHAR(3),
        currency VARCHAR(3) DEFAULT 'USD',
        description TEXT,
        website TEXT,
        logo_url TEXT,
        primary_ticker VARCHAR(10) UNIQUE,
        raw_source_data JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP DEFAULT NOW(),
        is_active BOOLEAN DEFAULT TRUE
    )

    asset_tickers (
        id BIGSERIAL PRIMARY KEY,
        asset_id BIGINT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
        ticker VARCHAR(10) NOT NULL,
        exchange VARCHAR(20),
        is_primary BOOLEAN DEFAULT FALSE,
        active_from TIMESTAMP DEFAULT NOW(),
        active_to TIMESTAMP,
        UNIQUE (asset_id, ticker, exchange)
    )
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.config.database import Base


class Asset(Base):
    """Canonical asset entity (company, ETF, crypto, index, commodity)."""
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    # Asset classification
    asset_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="stock",
        comment="stock | etf | crypto | index | commodity",
    )
    sector: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    industry: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Market identifiers
    exchange: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), server_default="USD", nullable=True)
    primary_ticker: Mapped[Optional[str]] = mapped_column(String(10), unique=True, nullable=True)

    # Metadata
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Source of truth for metadata (last profile data from Finnhub/yfinance)
    raw_source_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # AI analysis configuration (per-asset overrides for the automated worker)
    analysis_window_days: Mapped[int] = mapped_column(
        Integer,
        server_default="7",
        default=7,
        comment="Days back to look for articles in automated reports (1-90)",
    )
    max_articles_per_analysis: Mapped[int] = mapped_column(
        Integer,
        server_default="15",
        default=15,
        comment="Max articles to feed LLM per analysis run (5-30)",
    )

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="TRUE", default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    # Relationships
    tickers = relationship("AssetTicker", back_populates="asset", cascade="all, delete-orphan")
    company_reports = relationship("AICompanyReport", back_populates="asset", cascade="all, delete-orphan")

    # Indexes for common query patterns
    __table_args__ = (
        Index("idx_assets_type", "asset_type"),
        Index("idx_assets_sector", "sector"),
        Index("idx_assets_slug", "slug"),
        Index("idx_assets_primary_ticker", "primary_ticker"),
    )

    def __repr__(self):
        return f"<Asset id={self.id} ticker={self.primary_ticker} name={self.name} type={self.asset_type}>"


class AssetTicker(Base):
    """Maps alternate tickers/symbols to an Asset entity."""
    __tablename__ = "asset_tickers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    ticker: Mapped[str] = mapped_column(String(10), nullable=False)
    exchange: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, server_default="FALSE", default=False)
    active_from: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    active_to: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Relationship
    asset = relationship("Asset", back_populates="tickers")

    __table_args__ = (
        UniqueConstraint("asset_id", "ticker", "exchange", name="uq_asset_ticker_exchange"),
        Index("idx_asset_tickers_lookup", "ticker"),
    )

    def __repr__(self):
        return f"<AssetTicker asset_id={self.asset_id} ticker={self.ticker} primary={self.is_primary}>"
