"""Request-scoped local prompt selector and production-safety contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.config.database import get_async_session
from backend.config.settings import Settings
from backend.models.analysis import FinancialAnalysisResponse
from backend.routers import analysis as analysis_router
from backend.services import ollama_service


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

    def response():
        return FinancialAnalysisResponse(
            asset="TEST",
            overall_sentiment="Neutral",
            confidence_score=50,
            investment_rating="Hold",
            executive_summary="Deterministic selector fixture.",
        )

    v2 = SimpleNamespace(
        version="2.0",
        generate=AsyncMock(side_effect=lambda *_args, **_kwargs: response()),
        prompt_hash=lambda _request: "2" * 64,
    )
    v3 = SimpleNamespace(
        version="3.0",
        generate=AsyncMock(side_effect=lambda *_args, **_kwargs: response()),
        prompt_hash=lambda _request: "3" * 64,
    )
    pipelines = {"2.0": v2, "3.0": v3}
    persist = AsyncMock(return_value=77)
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

    monkeypatch.setattr(
        analysis_router, "get_current_analysis_prompt_pipeline", lambda: v2
    )
    monkeypatch.setattr(
        analysis_router,
        "get_analysis_prompt_pipeline",
        lambda version: pipelines[version],
    )
    monkeypatch.setattr(analysis_router, "create_report", persist)
    monkeypatch.setattr(analysis_router, "get_hybrid_stock_price", price)
    monkeypatch.setattr(
        analysis_router,
        "resolve_provider_model",
        lambda *_args: ("ollama", "fixture-model"),
    )
    monkeypatch.setattr(analysis_router, "_get_timeout_for_model", lambda *_: 30)

    app = FastAPI()
    app.include_router(analysis_router.router)
    app.dependency_overrides[get_async_session] = test_session
    return TestClient(app), session, pipelines, persist, price


def _payload(prompt_version=...):
    payload = {
        "ticker": "TEST",
        "max_articles": 1,
        "days_back": 3,
        "model": "fixture-model",
        "provider": "ollama",
        "article_ids": [1],
    }
    if prompt_version is not ...:
        payload["prompt_version"] = prompt_version
    return payload


def test_backend_override_setting_defaults_false_and_requires_explicit_true(monkeypatch):
    monkeypatch.delenv("ALLOW_PROMPT_VERSION_OVERRIDE", raising=False)
    assert Settings().ALLOW_PROMPT_VERSION_OVERRIDE is False
    monkeypatch.setenv("ALLOW_PROMPT_VERSION_OVERRIDE", "true")
    assert Settings().ALLOW_PROMPT_VERSION_OVERRIDE is True


def test_selector_resolves_existing_immutable_registry_descriptors(monkeypatch):
    monkeypatch.setenv("ALLOW_PROMPT_VERSION_OVERRIDE", "true")

    omitted = analysis_router._resolve_analysis_prompt_pipeline(None)
    explicit_v2 = analysis_router._resolve_analysis_prompt_pipeline("2.0")
    explicit_v3 = analysis_router._resolve_analysis_prompt_pipeline("3.0")

    assert omitted is explicit_v2 is ollama_service.get_analysis_prompt_pipeline("2.0")
    assert explicit_v2.generator is ollama_service.generate_analysis_v2
    assert explicit_v3 is ollama_service.get_analysis_prompt_pipeline("3.0")
    assert explicit_v3.generator is ollama_service.generate_analysis


@pytest.mark.parametrize(
    ("requested", "expected_version"),
    [(..., "2.0"), ("2.0", "2.0"), ("3.0", "3.0")],
)
def test_enabled_override_couples_execution_version_and_hash(
    monkeypatch, requested, expected_version
):
    monkeypatch.setenv("ALLOW_PROMPT_VERSION_OVERRIDE", "true")
    client, session, pipelines, persist, _price = _endpoint_harness(monkeypatch)

    response = client.post("/api/analysis/analyze_ticker", json=_payload(requested))

    assert response.status_code == 200
    selected = pipelines[expected_version]
    selected.generate.assert_awaited_once()
    for version, pipeline in pipelines.items():
        if version != expected_version:
            pipeline.generate.assert_not_awaited()
    persisted = persist.await_args.kwargs
    assert persisted["prompt_version"] == selected.version == expected_version
    assert persisted["prompt_hash"] == expected_version[0] * 64
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("requested", [..., "2.0"])
def test_production_default_and_explicit_v2_use_v2(monkeypatch, requested):
    monkeypatch.delenv("ALLOW_PROMPT_VERSION_OVERRIDE", raising=False)
    client, session, pipelines, persist, _price = _endpoint_harness(monkeypatch)

    response = client.post("/api/analysis/analyze_ticker", json=_payload(requested))

    assert response.status_code == 200
    pipelines["2.0"].generate.assert_awaited_once()
    pipelines["3.0"].generate.assert_not_awaited()
    assert persist.await_args.kwargs["prompt_version"] == "2.0"
    session.commit.assert_awaited_once()


def test_unauthorized_v3_is_rejected_before_provider_or_persistence(monkeypatch):
    monkeypatch.delenv("ALLOW_PROMPT_VERSION_OVERRIDE", raising=False)
    client, session, pipelines, persist, price = _endpoint_harness(monkeypatch)

    response = client.post(
        "/api/analysis/analyze_ticker", json=_payload("3.0")
    )

    assert response.status_code == 403
    assert "not available" in response.json()["detail"]
    session.execute.assert_not_awaited()
    price.assert_not_awaited()
    pipelines["2.0"].generate.assert_not_awaited()
    pipelines["3.0"].generate.assert_not_awaited()
    persist.assert_not_awaited()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("invalid", [1.0, 4.0, "v3", 3, True])
def test_invalid_versions_fail_typed_validation_without_side_effects(
    monkeypatch, invalid
):
    monkeypatch.setenv("ALLOW_PROMPT_VERSION_OVERRIDE", "true")
    client, session, pipelines, persist, price = _endpoint_harness(monkeypatch)

    response = client.post("/api/analysis/analyze_ticker", json=_payload(invalid))

    assert response.status_code == 422
    session.execute.assert_not_awaited()
    price.assert_not_awaited()
    pipelines["2.0"].generate.assert_not_awaited()
    pipelines["3.0"].generate.assert_not_awaited()
    persist.assert_not_awaited()
    session.commit.assert_not_awaited()
