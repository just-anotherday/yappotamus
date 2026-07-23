"""
AI Job Queue ORM Model — In-database job queue for all asynchronous AI processing.

Every AI enrichment task (article summary, company report, sector report, market report)
is queued here with a status lifecycle: pending -> processing -> completed/failed.

The background worker polls this table continuously for pending jobs, ensuring no page
request ever triggers expensive AI processing synchronously.

Table:
    ai_job_queue (
        id BIGSERIAL PRIMARY KEY,
        job_type VARCHAR(30) NOT NULL,
        target_id INTEGER NOT NULL,         -- article_id / asset_id etc.
        target_type VARCHAR(20) NOT NULL,   -- 'article' | 'asset' | 'sector' | 'market'
        priority INTEGER DEFAULT 10,
        status VARCHAR(20) DEFAULT 'pending',
        payload JSONB,
        result JSONB,
        error_message TEXT,
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        scheduled_for TIMESTAMP DEFAULT NOW(),
        started_at TIMESTAMP,
        completed_at TIMESTAMP,
        created_at TIMESTAMP DEFAULT NOW()
    )
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Integer, String, Text, func, Index
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from backend.config.database import Base


class AIJobQueue(Base):
    """In-database job queue for async AI processing."""
    __tablename__ = "ai_job_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Job classification
    job_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="article_summary | company_report | sector_report | market_report | embedding",
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    target_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="'article' | 'asset' | 'sector' | 'market'",
    )
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)

    # Priority (lower = higher priority)
    priority: Mapped[int] = mapped_column(Integer, server_default="10", default=10)

    # Lifecycle status
    status: Mapped[str] = mapped_column(
        String(20),
        server_default="pending",
        comment="'pending' | 'processing' | 'completed' | 'failed'",
    )

    # Input / Output
    payload: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    result: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Retry tracking
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0", default=0)
    max_retries: Mapped[int] = mapped_column(Integer, server_default="3", default=3)

    # Timing
    scheduled_for: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # Indexes: the worker polls for pending jobs ordered by priority + scheduled_for
    __table_args__ = (
        Index("idx_ai_job_queue_status_priority", "status", "priority"),
        Index("idx_ai_job_queue_scheduled", "scheduled_for"),
        Index("idx_ai_job_queue_target", "target_type", "target_id"),
        Index("idx_ai_job_queue_job_type", "job_type"),
        Index("idx_ai_job_queue_dedupe", "job_type", "dedupe_key", "status"),
    )

    def __repr__(self):
        return f"<AIJob id={self.id} type={self.job_type} status={self.status} target={self.target_type}:{self.target_id}>"
