"""Regression coverage for bounded after-hours analysis market data."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from backend.models.analysis import ArticleReference, FinancialAnalysisResponse
from backend.routers import analysis as analysis_router
from backend.services import hybrid_data_service, yfinance_fallback


@pytest.mark.asyncio
async def test_closed_market_regular_provider_price_remains_usable(monkeypatch):
    async def closed_quote(ticker: str):
        return {
            "ticker": ticker,
            "symbol": ticker,
            "company_name": "SPCX Corp",
            "current_price": 100.0,
            "previous_close": 99.0,
            "market_cap": 1_000_000,
            "data_source": "fh",
            "security_type": "STOCK",
        }

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", closed_quote)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", AsyncMock(return_value=None))
    hybrid_data_service._cache.clear()

    result = await hybrid_data_service.get_hybrid_stock_price("SPCX")

    assert result is not None
    assert result["current_price"] == 100.0
    assert result["previous_close"] == 99.0


def test_yfinance_retains_post_market_provenance():
    fields = yfinance_fallback._assemble_price_fields(
        {
            "currentPrice": 100.5,
            "regularMarketPrice": 100.0,
            "previousClose": 98.0,
            "postMarketPrice": 101.0,
            "postMarketChange": 1.0,
            "postMarketChangePercent": 1.0,
        }
    )

    assert fields["current_price"] == 101.0
    assert fields["post_market_price"] == 101.0
    assert fields["post_market_change"] == 1.0
    assert fields["post_market_change_percent"] == 1.0
    assert fields["regular_close"] == 100.0
    assert fields["market_session"] == "after_hours"
    assert fields["price_source"] == "post_market_price"


def test_yfinance_uses_regular_price_when_post_market_quote_is_absent():
    fields = yfinance_fallback._assemble_price_fields(
        {
            "currentPrice": 100.0,
            "regularMarketPrice": 100.0,
            "previousClose": 99.0,
        }
    )

    assert fields["current_price"] == 100.0
    assert fields["previous_close"] == 99.0
    assert fields["post_market_price"] is None
    assert fields["market_session"] is None


@pytest.mark.asyncio
async def test_true_provider_exhaustion_has_no_unbounded_market_fallback(
    monkeypatch,
):
    async def no_finnhub(_ticker):
        return None

    monkeypatch.setattr(hybrid_data_service, "finnhub_get_stock_price", no_finnhub)
    monkeypatch.setattr(hybrid_data_service, "_yf_async", AsyncMock(return_value=None))
    hybrid_data_service._cache.clear()

    result = await hybrid_data_service.get_hybrid_stock_price("SPCX")

    assert result is None


def _article():
    return SimpleNamespace(
        id=1,
        title="Trusted SPCX article",
        summary="Trusted summary.",
        provider_name="Trusted Wire",
        article_url="https://trusted.example/spcx",
        pub_date=None,
    )


def _pipeline(version: str):
    result = FinancialAnalysisResponse(
        asset="SPCX",
        overall_sentiment="Neutral",
        confidence_score=60,
        investment_rating="Hold",
        articles_used=[
            ArticleReference(
                title="Trusted SPCX article",
                url="https://trusted.example/spcx",
                published_at=None,
            )
        ],
        executive_summary="Deterministic fixture.",
    )
    return SimpleNamespace(
        version=version,
        generate=AsyncMock(return_value=result),
        prompt_hash=lambda _request: "a" * 64,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("prompt_version", ["2.0", "3.0"])
async def test_after_hours_snapshot_is_prompt_version_independent(
    monkeypatch,
    prompt_version,
):
    article = _article()

    async def execute(_statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [article]))

    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    pipeline = _pipeline(prompt_version)
    market_data = AsyncMock(
        return_value={
            "current_price": 101.0,
            "previous_close": 100.0,
            "regular_close": 100.0,
            "post_market_price": 101.0,
            "post_market_change": 1.0,
            "post_market_change_percent": 1.0,
            "market_session": "after_hours",
            "price_source": "post_market_price",
            "company_name": "SPCX Corp",
            "volume": 1_000,
        }
    )
    persist = AsyncMock(return_value=77)
    monkeypatch.setattr(
        analysis_router,
        "_resolve_analysis_prompt_pipeline",
        lambda _: pipeline,
    )
    monkeypatch.setattr(analysis_router, "get_hybrid_stock_price", market_data)
    monkeypatch.setattr(analysis_router, "create_report", persist)
    monkeypatch.setattr(
        analysis_router,
        "resolve_provider_model",
        lambda *_: ("ollama", "fixture"),
    )
    monkeypatch.setattr(analysis_router, "_get_timeout_for_model", lambda *_: 30)

    result = await analysis_router.analysis_analyze_ticker(
        ticker="SPCX",
        max_articles=1,
        days_back=3,
        model="fixture",
        provider="ollama",
        prompt_version=prompt_version,
        article_ids=[1],
        session=session,
    )

    assert result.report_id == 77
    market_data.assert_awaited_once_with("SPCX")
    generated = pipeline.generate.await_args.args[0]
    assert generated.price_data.current_price == 101.0
    assert generated.price_data.daily_change_percent == 1.0
    assert persist.await_args.kwargs["current_price_at_analysis"] == 101.0
    assert persist.await_args.kwargs["prompt_version"] == prompt_version


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "market_payload",
    [None, {}, {"current_price": None}, {"current_price": 0.0}],
)
async def test_true_provider_exhaustion_is_503_before_ai_or_persistence(
    monkeypatch,
    market_payload,
):
    article = _article()

    async def execute(_statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [article]))

    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    pipeline = _pipeline("2.0")
    persist = AsyncMock()
    monkeypatch.setattr(
        analysis_router,
        "_resolve_analysis_prompt_pipeline",
        lambda _: pipeline,
    )
    monkeypatch.setattr(
        analysis_router,
        "get_hybrid_stock_price",
        AsyncMock(return_value=market_payload),
    )
    monkeypatch.setattr(analysis_router, "create_report", persist)

    with pytest.raises(HTTPException) as exc_info:
        await analysis_router.analysis_analyze_ticker(
            ticker="SPCX",
            max_articles=1,
            days_back=3,
            model="fixture",
            provider="ollama",
            prompt_version="2.0",
            article_ids=[1],
            session=session,
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "Could not fetch market data for SPCX"
    pipeline.generate.assert_not_awaited()
    persist.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_ticker_remains_404_before_market_or_ai(monkeypatch):
    async def execute(_statement):
        return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: []))

    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    pipeline = _pipeline("2.0")
    market_data = AsyncMock()
    persist = AsyncMock()
    monkeypatch.setattr(
        analysis_router,
        "_resolve_analysis_prompt_pipeline",
        lambda _: pipeline,
    )
    monkeypatch.setattr(analysis_router, "get_hybrid_stock_price", market_data)
    monkeypatch.setattr(analysis_router, "create_report", persist)

    with pytest.raises(HTTPException) as exc_info:
        await analysis_router.analysis_analyze_ticker(
            ticker="NOTREAL",
            max_articles=1,
            days_back=3,
            model="fixture",
            provider="ollama",
            prompt_version="2.0",
            article_ids=[1],
            session=session,
        )

    assert exc_info.value.status_code == 404
    market_data.assert_not_awaited()
    pipeline.generate.assert_not_awaited()
    persist.assert_not_awaited()
    session.commit.assert_not_awaited()
