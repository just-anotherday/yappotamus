"""Durable lease, checkpoint, and health state for production news ingestion."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.config.database import Base


class NewsIngestionState(Base):
    __tablename__ = "news_ingestion_state"
    __table_args__ = (
        CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_news_ingestion_failures_nonnegative",
        ),
        Index("idx_news_ingestion_state_lease_expires", "lease_expires_at"),
    )

    job_name: Mapped[str] = mapped_column(String(64), primary_key=True)
    last_attempted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_successful_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_successful_window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_article_retrieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_article_inserted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latest_retrieved_pub_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latest_inserted_pub_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_status: Mapped[Optional[str]] = mapped_column(String(32))
    last_error_code: Mapped[Optional[str]] = mapped_column(String(64))
    last_metrics: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    lease_owner: Mapped[Optional[str]] = mapped_column(Text)
    lease_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
