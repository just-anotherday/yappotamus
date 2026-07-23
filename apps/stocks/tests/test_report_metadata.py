"""Regression coverage for saved report prompt metadata and timestamps."""

from datetime import datetime, timezone

from backend.models.analysis import FinancialAnalysisRequest, PriceDataRequest
from backend.models.report_schemas import AnalysisReportDetail, ReportSummaryOut
from backend.services.ollama_service import (
    CURRENT_PROMPT_VERSION,
    get_effective_prompt_hash,
)


def test_report_summary_returns_prompt_metadata_and_creation_time():
    created_at = datetime(2026, 7, 21, 20, 14, tzinfo=timezone.utc)
    summary = ReportSummaryOut(
        id=184,
        report_number=1,
        ticker="AMD",
        overall_sentiment="Bullish",
        confidence_score=72,
        articles_count=14,
        model_used="example-model",
        prompt_version=CURRENT_PROMPT_VERSION,
        prompt_hash="a" * 64,
        created_at=created_at,
    ).model_dump(mode="json")

    assert summary["prompt_version"] == CURRENT_PROMPT_VERSION
    assert summary["prompt_hash"] == "a" * 64
    serialized_created_at = datetime.fromisoformat(summary["created_at"].replace("Z", "+00:00"))
    assert serialized_created_at == created_at
    assert serialized_created_at.utcoffset() == timezone.utc.utcoffset(created_at)


def test_report_detail_returns_same_prompt_metadata_and_creation_time():
    created_at = datetime(2026, 7, 21, 20, 14, tzinfo=timezone.utc)
    detail = AnalysisReportDetail(
        id=184,
        ticker="AMD",
        report_data={"overall_sentiment": "Bullish"},
        articles_count=14,
        model_used="example-model",
        prompt_version=CURRENT_PROMPT_VERSION,
        prompt_hash="b" * 64,
        created_at=created_at,
    ).model_dump(mode="json")

    assert detail["prompt_version"] == CURRENT_PROMPT_VERSION
    assert detail["prompt_hash"] == "b" * 64
    serialized_created_at = datetime.fromisoformat(detail["created_at"].replace("Z", "+00:00"))
    assert serialized_created_at == created_at
    assert serialized_created_at.utcoffset() == timezone.utc.utcoffset(created_at)


def test_effective_prompt_hash_is_deterministic_and_payload_sensitive():
    request = FinancialAnalysisRequest(
        ticker="AMD",
        news_articles=[],
        price_data=PriceDataRequest(
            current_price=100,
            daily_change_percent=1,
            fifty_two_week_high=120,
            fifty_two_week_low=80,
            trading_volume=1_000,
        ),
        analysis_date="2026-07-21T20:14:00+00:00",
    )

    first = get_effective_prompt_hash(request)
    second = get_effective_prompt_hash(request)
    changed = get_effective_prompt_hash(request.model_copy(update={"ticker": "NVDA"}))

    assert len(first) == 64
    assert first == second
    assert first != changed