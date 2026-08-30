"""Regression coverage for saved report prompt metadata and timestamps."""

from datetime import datetime, timezone

import pytest

from backend.models.analysis import FinancialAnalysisRequest, PriceDataRequest
from backend.models.report_schemas import AnalysisReportDetail, ReportSummaryOut
from backend.services import report_service
from backend.services.ollama_service import (
    CURRENT_PROMPT_VERSION,
    get_current_analysis_prompt_pipeline,
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
        articles_cited_count=6,
        model_used="example-model",
        prompt_version=CURRENT_PROMPT_VERSION,
        prompt_hash="a" * 64,
        created_at=created_at,
    ).model_dump(mode="json")

    assert summary["prompt_version"] == CURRENT_PROMPT_VERSION
    assert summary["prompt_hash"] == "a" * 64
    assert summary["articles_count"] == 14
    assert summary["articles_cited_count"] == 6
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

    pipeline = get_current_analysis_prompt_pipeline()
    first = pipeline.prompt_hash(request)
    second = pipeline.prompt_hash(request)
    changed = pipeline.prompt_hash(request.model_copy(update={"ticker": "NVDA"}))

    assert pipeline.version == CURRENT_PROMPT_VERSION == "2.0"
    assert len(first) == 64
    assert first == second
    assert first != changed


class _CapturingSession:
    def __init__(self):
        self.added = None

    def add(self, value):
        self.added = value

    async def flush(self):
        self.added.id = 901


@pytest.mark.asyncio
async def test_report_creation_persists_an_explicit_utc_wall_clock(monkeypatch):
    generated_at_utc = datetime(2026, 8, 20, 17, 35)
    monkeypatch.setattr(
        report_service,
        "utc_now_naive",
        lambda: generated_at_utc,
    )
    session = _CapturingSession()

    report_id = await report_service.create_report(
        session=session,
        ticker="AMD",
        report_data={"overall_sentiment": "Bullish", "articles_used": []},
        articles_count=35,
        model_used="test-model",
        prompt_version="3.0",
    )

    assert report_id == 901
    assert session.added.created_at == generated_at_utc
    assert session.added.created_at.tzinfo is None
    assert report_service.count_cited_articles(session.added.report_data) == 0


def test_cited_article_count_is_derived_safely_for_current_and_legacy_reports():
    current = {"articles_used": [{"title": f"Article {index}"} for index in range(10)]}

    assert report_service.count_cited_articles(current) == 10
    assert report_service.count_cited_articles({}) == 0
    assert report_service.count_cited_articles({"articles_used": None}) == 0
    assert report_service.count_cited_articles(None) == 0
