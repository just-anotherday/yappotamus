"""
SQLAlchemy ORM model for the news_articles PostgreSQL table.

All articles are ingested via Finnhub's API. The data_source column was removed since
yfinance news pipeline was eliminated (migrated during Phase 1). The author column
was also removed since Finnhub does not provide author names (<1% of records had values).

Maps to:
    news_articles (
        id BIGSERIAL PRIMARY KEY,
        finnhub_id TEXT UNIQUE,
        ticker VARCHAR(10),
        title TEXT,
        summary TEXT,
        provider_name TEXT,
        article_url TEXT UNIQUE,
        thumbnail_url TEXT,
        pub_date TIMESTAMP,
        raw_json JSONB,
        imported_at TIMESTAMP DEFAULT NOW()
    )
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Text, DateTime, Index, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.config.database import Base


class NewsArticle(Base):
    __tablename__ = "news_articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    finnhub_id: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    ticker: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider_name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    article_url: Mapped[Optional[str]] = mapped_column(Text, unique=True, nullable=True)
    thumbnail_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    pub_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSONB, name="raw_json", nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Database indexes for common query patterns
    __table_args__ = (
        Index("idx_news_articles_pub_date", "pub_date"),
        Index("idx_news_articles_ticker_pub_date", "ticker", "pub_date"),
        Index("idx_news_articles_imported_at", "imported_at"),
    )
