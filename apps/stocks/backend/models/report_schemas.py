"""Pydantic schemas for analysis reports.

ReportSummaryOut — slim DTO for list endpoints (no full JSON payload)
AnalysisReportDetail — full DTO with complete report_data
CreateReportResponse — returned after saving a new report
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict


class ReportSummaryOut(BaseModel):
    """Slim representation for list pagination."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_number: int  # Consecutive rank by created_at (1=newest when sorted desc)
    ticker: str
    overall_sentiment: str
    confidence_score: int
    articles_count: int
    current_price_at_analysis: Optional[float] = None
    model_used: str
    created_at: datetime


class ReportPaginationResponse(BaseModel):
    """Paginated list of report summaries."""

    items: List[ReportSummaryOut]
    total: int
    page: int
    limit: int
    has_more: bool


class AnalysisReportDetail(BaseModel):
    """Full report detail including the complete JSON payload."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticker: str
    report_data: Dict[str, Any]
    articles_count: int
    model_used: str
    prompt_version: str
    current_price_at_analysis: Optional[float] = None
    created_at: datetime


class CreateReportResponse(BaseModel):
    """Returned immediately after saving a new analysis."""

    report_id: int
    report: Dict[str, Any]
