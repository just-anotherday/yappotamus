"""
Pydantic schemas for news article API I/O validation.

All articles are ingested via Finnhub API only (yfinance pipeline removed in Phase 1).
`data_source` and `author` fields were removed from the model.
"""

from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, field_serializer

from backend.lib.timestamps import utc_isoformat


class NewsArticleOut(BaseModel):
    """Response schema for a single news article."""
    id: int
    finnhub_id: Optional[str] = None
    ticker: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    provider_name: Optional[str] = None
    article_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    pub_date: Optional[datetime] = None
    imported_at: Optional[datetime] = None

    @field_serializer("pub_date", "imported_at", when_used="json")
    def serialize_timestamps(self, value: Optional[datetime]) -> Optional[str]:
        """Make the UTC-naive database convention explicit on the wire."""

        return utc_isoformat(value)

    model_config = {"from_attributes": True}


class NewsPaginatedResponse(BaseModel):
    """Paginated response wrapper for news articles."""
    articles: list[NewsArticleOut]
    total: int
    page: int
    limit: int
    has_more: bool


class NewsArticleIngest(BaseModel):
    """Schema for ingesting a single article from Finnhub."""
    finnhub_id: Optional[str] = None
    ticker: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    provider_name: Optional[str] = None
    article_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    pub_date: Optional[datetime] = None
    raw_json: Optional[dict[str, Any]] = None
