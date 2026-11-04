"""Account research data and durable daily report execution history."""
from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, Text, func, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from backend.config.database import Base


class ResearchNote(Base):
    __tablename__ = "research_notes"
    owner_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), primary_key=True)
    text: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ArticleReadingState(Base):
    __tablename__ = "article_reading_state"
    owner_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    article_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    saved: Mapped[bool] = mapped_column(Boolean, default=False)
    read: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportRun(Base):
    __tablename__ = "report_runs"
    __table_args__ = (Index("report_runs_one_active", text("(1)"), unique=True, postgresql_where=text("status IN ('queued', 'running')")),)
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String(20), default="daily")
    parent_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stage: Mapped[str] = mapped_column(String(50), default="queued")
    current_ticker: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tickers: Mapped[list] = mapped_column(JSONB, default=list)
    outcomes: Mapped[list] = mapped_column(JSONB, default=list)
    news_counts: Mapped[dict] = mapped_column(JSONB, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
