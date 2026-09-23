"""Trusted-boundary ticker validation contracts for analysis requests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config.database import get_async_session
from backend.lib.tickers import normalize_ticker as canonical_normalize_ticker
from backend.models.analysis import FinancialAnalysisResponse
from backend.routers import analysis as analysis_router


def _endpoint_harness(monkeypatch):
    article = SimpleNamespace(
        id=1,
        title="Trusted database article",
        summary="Trusted database summary.",
        provider_name="Trusted Wire",
        article_url="https://trusted.example/test",
        pub_date=None,
    )
    session = SimpleNamespace(
        execute=AsyncMock(
            return_value=SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [article])
            )
        ),
        commit=AsyncMock(),
    )

    async def test_session():
        yield session

    generated_tickers = []

    async def generate(request, **_kwargs):
        generated_tickers.append(request.ticker)
        return FinancialAnalysisResponse(
            asset=request.ticker,
            overall_sentiment="Neutral",
            confidence_score=50,
            investment_rating="Hold",
            executive_summary="Deterministic ticker-validation fixture.",
        )

    pipelines = {
        version: SimpleNamespace(
            version=version,
            generate=AsyncMock(side_effect=generate),
            prompt_hash=lambda _request, version=version: version[0] * 64,
        )
        for version in ("2.0", "3.0")
    }
    default_selector = Mock(return_value=pipelines["2.0"])
    version_selector = Mock(side_effect=lambda version: pipelines[version])
    price = AsyncMock(
        return_value={
            "current_price": 100.0,
            "previous_close": 99.0,
            "fifty_two_week_high": 120.0,
            "fifty_two_week_low": 80.0,
            "volume": 1_000_000,
            "company_name": "Test Company",
        }
    )
    persist = AsyncMock(return_value=77)
    validator = Mock(side_effect=canonical_normalize_ticker)

    monkeypatch.setattr(
        analysis_router, "normalize_ticker", validator, raising=False
    )
    monkeypatch.setattr(
        analysis_router, "get_current_analysis_prompt_pipeline", default_selector
    )
    monkeypatch.setattr(
        analysis_router, "get_analysis_prompt_pipeline", version_selector
    )
    monkeypatch.setattr(analysis_router, "get_hybrid_stock_price", price)
    monkeypatch.setattr(analysis_router, "create_report", persist)
    monkeypatch.setattr(
        analysis_router,
        "resolve_provider_model",
        lambda *_args: ("ollama", "fixture-model"),
    )
    monkeypatch.setattr(analysis_router, "_get_timeout_for_model", lambda *_: 30)

    app = FastAPI()
    app.include_router(analysis_router.router)
    app.dependency_overrides[get_async_session] = test_session
    return SimpleNamespace(
        client=TestClient(app),
        session=session,
        pipelines=pipelines,
        default_selector=default_selector,
        version_selector=version_selector,
        price=price,
        persist=persist,
        validator=validator,
        generated_tickers=generated_tickers,
    )


def _payload(ticker, prompt_version=...):
    payload = {
        "ticker": ticker,
        "max_articles": 1,
        "days_back": 3,
        "model": "fixture-model",
        "provider": "ollama",
        "article_ids": [1],
    }
    if prompt_version is not ...:
        payload["prompt_version"] = prompt_version
    return payload


@pytest.mark.parametrize("prompt_version", [..., "2.0", "3.0"])
@pytest.mark.parametrize(
    "ticker",
    ["AMD!", "", "   ", "A MD", "AMD/US", "AMD;DROP", "ABCDEFGHIJK"],
)
def test_malformed_ticker_is_rejected_before_analysis_work(
    monkeypatch, ticker, prompt_version
):
    harness = _endpoint_harness(monkeypatch)

    response = harness.client.post(
        "/api/analysis/analyze_ticker",
        json=_payload(ticker, prompt_version),
    )

    assert response.status_code == 400
    assert response.json()["detail"].startswith("Invalid ticker")
    harness.validator.assert_called_once_with(ticker)
    harness.default_selector.assert_not_called()
    harness.version_selector.assert_not_called()
    harness.session.execute.assert_not_awaited()
    harness.price.assert_not_awaited()
    for pipeline in harness.pipelines.values():
        pipeline.generate.assert_not_awaited()
    harness.persist.assert_not_awaited()
    harness.session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    ("ticker", "normalized"),
    [("AMD", "AMD"), ("amd", "AMD"), ("AAPL", "AAPL"), ("  AMD  ", "AMD")],
)
@pytest.mark.parametrize("prompt_version", ["2.0", "3.0"])
def test_valid_ticker_is_normalized_before_existing_analysis_path(
    monkeypatch, ticker, normalized, prompt_version
):
    harness = _endpoint_harness(monkeypatch)

    response = harness.client.post(
        "/api/analysis/analyze_ticker",
        json=_payload(ticker, prompt_version),
    )

    assert response.status_code == 200
    harness.validator.assert_called_once_with(ticker)
    harness.version_selector.assert_called_once_with(prompt_version)
    harness.session.execute.assert_awaited_once()
    harness.price.assert_awaited_once_with(normalized)
    harness.pipelines[prompt_version].generate.assert_awaited_once()
    assert harness.generated_tickers == [normalized]
    persisted = harness.persist.await_args.kwargs
    assert persisted["ticker"] == normalized
    harness.persist.assert_awaited_once()
    harness.session.commit.assert_awaited_once()


@pytest.mark.parametrize("ticker", ["BRK.B", "BRK-B"])
def test_analysis_endpoint_preserves_canonical_special_symbol_policy(
    monkeypatch, ticker
):
    harness = _endpoint_harness(monkeypatch)

    response = harness.client.post(
        "/api/analysis/analyze_ticker", json=_payload(ticker, "3.0")
    )

    assert response.status_code == 400
    harness.session.execute.assert_not_awaited()
    harness.price.assert_not_awaited()
    harness.pipelines["3.0"].generate.assert_not_awaited()
    harness.persist.assert_not_awaited()
