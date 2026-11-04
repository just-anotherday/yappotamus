"""Durable outbound reports and idempotent inbound publication receipts."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.config.database import Base
from backend.lib.timestamps import utc_now_naive


class ReportPublication(Base):
    __tablename__ = "report_publications"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    report_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("analysis_reports.id", ondelete="CASCADE"), unique=True)
    target_url: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSONB)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now_naive, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    remote_report_id: Mapped[int | None] = mapped_column(BigInteger)
    last_error: Mapped[str | None] = mapped_column(String(100))


class ReportPublicationReceipt(Base):
    __tablename__ = "report_publication_receipts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    # Keep the receipt if a user deletes the report, so retries cannot resurrect it.
    report_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("analysis_reports.id", ondelete="SET NULL"))
    received_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
