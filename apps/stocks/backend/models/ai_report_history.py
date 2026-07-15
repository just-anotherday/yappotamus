"""
AI Report History Model — Audit trail for all company intelligence reports.

Every time a company report is generated or updated, a snapshot is saved here
so users can track how sentiment, confidence, and analysis have evolved over time.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Float, func, Index
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from backend.config.database import Base


class AICompanyReportHistory(Base):
    """Historical snapshot of a company AI report at the time it was generated."""
    __tablename__ = "ai_company_report_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # Reference to current report (FK, nullable if that report was later overwritten)
    original_report_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("ai_company_reports.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Denormalized ticker for quick lookups
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)

    # Snapshot of report metadata at this point in time
    overall_sentiment: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)
    articles_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    model_used: Mapped[str] = mapped_column(String(50), nullable=False, server_default="")
    prompt_version: Mapped[str] = mapped_column(String(20), nullable=False, server_default="1.0")
    price_snapshot: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    # Optional: store the full report_data for deep historical inspection
    report_data_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("idx_report_history_ticker_created", "ticker", "created_at"),
        Index("idx_report_history_ticker_sentiment", "ticker", "overall_sentiment"),
    )

    def __repr__(self):
        return f"<AICompanyReportHistory ticker={self.ticker} sentiment={self.overall_sentiment} at {self.created_at}>"
