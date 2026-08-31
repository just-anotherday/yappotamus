"""Deterministic contracts for the production Prompt v2 fallback."""

import hashlib
import json
from dataclasses import FrozenInstanceError
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from backend.models.analysis import (
    ArticleReference,
    FinancialAnalysisRequest,
    FinancialAnalysisResponse,
    FinancialAnalysisV2LLMResponse,
    NewsArticleRequest,
    PriceDataRequest,
)
from backend.models.report_schemas import AnalysisReportDetail
from backend.routers import analysis as analysis_router
from backend.services import ollama_service
from backend.services.ai.exceptions import AIStructuredOutputError


V2_PROVIDER_REQUIRED_FIELDS = {
    "asset",
    "overall_sentiment",
    "confidence_score",
    "investment_rating",
    "executive_summary",
    "news_summary",
    "key_catalysts",
    "key_risks",
    "bull_case",
    "bear_case",
    "market_reaction_analysis",
    "technical_analysis",
    "outlook",
    "actionable_insights",
    "portfolio_fit",
    "article_indices_used",
}


def _request() -> FinancialAnalysisRequest:
    return FinancialAnalysisRequest(
        ticker="TEST",
        company_name="Test Company",
        analysis_date="2026-08-30T12:00:00+00:00",
        news_articles=[
            NewsArticleRequest(
                title="Trusted first article",
                summary="Test Company announced a supplied development.",
                source="Trusted Wire",
                published_at="2026-08-30T10:00:00+00:00",
                url="https://trusted.example/first",
            ),
            NewsArticleRequest(
                title="Trusted second article",
                summary="Test Company shares moved after the development.",
                source="Trusted Market Wire",
                published_at="2026-08-30T11:00:00+00:00",
                url="https://trusted.example/second",
            ),
        ],
        price_data=PriceDataRequest(
            current_price=100.0,
            daily_change_percent=1.5,
            fifty_two_week_high=None,
            fifty_two_week_low=None,
            trading_volume=1_000_000,
            beta=None,
            support_level=None,
            resistance_level=None,
            moving_average_50=None,
            moving_average_200=None,
            market_cap=None,
        ),
    )


def _provider_payload(*, article_indices=...) -> dict:
    payload = {
        "asset": "PROVIDER-FORGED-ASSET",
        "overall_sentiment": "Neutral",
        "confidence_score": 60,
        "investment_rating": "Hold",
        "articles_used": [
            {
                "title": "PROVIDER FORGERY",
                "url": "https://attacker.invalid/forged",
                "published_at": "1900-01-01T00:00:00Z",
            }
        ],
        "news_summary": ["The supplied development is material."],
        "key_catalysts": ["Execution could support the company."],
        "key_risks": [{"risk": "Execution risk remains.", "severity": "Medium"}],
        "bull_case": ["Successful execution could support the outlook."],
        "bear_case": ["Execution setbacks could pressure the outlook."],
        "market_reaction_analysis": "Shares moved after the development.",
        "technical_analysis": {
            "trend": "Insufficient supplied technical data.",
            "support_levels": [],
            "resistance_levels": [],
            "breakout_level": "N/A",
            "breakdown_level": "N/A",
        },
        "outlook": {
            "short_term": "Neutral — evidence remains limited.",
            "medium_term": "Neutral — execution remains important.",
            "long_term": "Neutral — fundamentals were not supplied.",
        },
        "actionable_insights": ["Monitor execution."],
        "portfolio_fit": "Potential satellite exposure with execution risk.",
        "executive_summary": "The supplied evidence supports a neutral stance.",
        "current_price_at_analysis": -999.0,
        "report_id": 999_999,
    }
    if article_indices is not ...:
        payload["article_indices_used"] = article_indices
    return payload


async def _run_v2(monkeypatch, payload: dict, *, requested_version=None):
    client = SimpleNamespace(generate=AsyncMock(return_value=json.dumps(payload)))

    async def validate_provider_model(provider_id, model_name):
        assert provider_id == "ollama"
        assert model_name == "fixture-model"
        return "ollama", "fixture-model", client

    monkeypatch.setattr(
        "backend.services.ai.ai_service.validate_provider_model",
        validate_provider_model,
    )
    pipeline = (
        ollama_service.get_current_analysis_prompt_pipeline()
        if requested_version is None
        else analysis_router._resolve_analysis_prompt_pipeline(requested_version)
    )
    result = await pipeline.generate(
        _request(), provider="ollama", model="fixture-model"
    )
    return pipeline, client, result


def test_active_registry_is_immutable_and_selects_v2_while_retaining_v3():
    current = ollama_service.get_current_analysis_prompt_pipeline()
    v3 = ollama_service.get_analysis_prompt_pipeline(
        ollama_service.PROMPT_V3_VERSION
    )

    assert ollama_service.CURRENT_PROMPT_VERSION == "2.0"
    assert current.version == ollama_service.PROMPT_V2_VERSION == "2.0"
    assert current.generator is ollama_service.generate_analysis_v2
    assert v3.version == "3.0"
    assert v3.generator is ollama_service.generate_analysis
    assert current.structured_output_contract != v3.structured_output_contract
    with pytest.raises(TypeError):
        ollama_service.ANALYSIS_PROMPT_PIPELINES["4.0"] = current
    with pytest.raises(FrozenInstanceError):
        current.version = "3.0"


@pytest.mark.asyncio
async def test_explicit_local_v2_uses_only_primary_generation_and_bypasses_all_v3_stages(
    monkeypatch,
):
    monkeypatch.setenv("ALLOW_PROMPT_VERSION_OVERRIDE", "true")
    review = AsyncMock(side_effect=AssertionError("v3 reviewer invoked"))
    correction = AsyncMock(side_effect=AssertionError("v3 correction invoked"))
    registry = MagicMock(side_effect=AssertionError("v3 target registry invoked"))
    monkeypatch.setattr(ollama_service, "_run_grounding_review", review)
    monkeypatch.setattr(ollama_service, "generate_correction_patch_set", correction)
    monkeypatch.setattr(ollama_service, "build_correction_target_registry", registry)

    pipeline, client, result = await _run_v2(
        monkeypatch,
        _provider_payload(article_indices=[1]),
        requested_version="2.0",
    )

    assert pipeline.version == "2.0"
    client.generate.assert_awaited_once()
    review.assert_not_awaited()
    correction.assert_not_awaited()
    registry.assert_not_called()
    assert isinstance(result, FinancialAnalysisResponse)
    assert FinancialAnalysisResponse.model_validate(result.model_dump()) == result


def test_v2_prompt_renders_missing_optional_market_fields_without_fabrication():
    prompt = ollama_service._build_v2_user_prompt(_request())

    assert "52-Week High: Unavailable" in prompt
    assert "52-Week Low: Unavailable" in prompt
    assert "Support Level:" not in prompt
    assert "Resistance Level:" not in prompt
    assert "50-Day MA:" not in prompt
    assert "200-Day MA:" not in prompt
    assert "None" not in prompt
    assert "Never reinterpret 52-week highs or lows as support or resistance" in (
        ollama_service.PROMPT_V2_SYSTEM_PROMPT
    )


def test_v2_provider_schema_requires_the_complete_nonempty_historical_body():
    schema = FinancialAnalysisV2LLMResponse.model_json_schema()

    assert set(schema["required"]) == V2_PROVIDER_REQUIRED_FIELDS
    assert schema == ollama_service._build_v2_response_schema()
    assert set(schema["properties"]) == V2_PROVIDER_REQUIRED_FIELDS
    assert "articles_used" not in schema["properties"]
    assert "current_price_at_analysis" not in schema["properties"]
    assert "report_id" not in schema["properties"]

    for field in (
        "news_summary",
        "key_catalysts",
        "key_risks",
        "bull_case",
        "bear_case",
        "actionable_insights",
    ):
        assert schema["properties"][field]["minItems"] == 1
    for field in (
        "asset",
        "executive_summary",
        "market_reaction_analysis",
        "portfolio_fit",
    ):
        assert schema["properties"][field]["minLength"] == 1
    risk_schema = schema["$defs"]["FinancialAnalysisV2LLMRisk"]
    assert risk_schema["properties"]["risk"]["minLength"] == 1
    assert risk_schema["properties"]["severity"]["enum"] == [
        "Low",
        "Medium",
        "High",
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "asset": "SPCX",
            "overall_sentiment": "Neutral",
            "confidence_score": 50,
        },
        {
            "asset": "SPCX",
            "overall_sentiment": "Neutral",
            "confidence_score": 50,
            "investment_rating": "Hold",
            "executive_summary": "",
            "news_summary": [],
            "key_catalysts": [],
            "key_risks": [],
            "bull_case": [],
            "bear_case": [],
            "market_reaction_analysis": "",
            "technical_analysis": {
                "trend": "",
                "support_levels": [],
                "resistance_levels": [],
                "breakout_level": "",
                "breakdown_level": "",
            },
            "outlook": {
                "short_term": "",
                "medium_term": "",
                "long_term": "",
            },
            "actionable_insights": [],
            "portfolio_fit": "",
            "article_indices_used": [],
        },
    ],
    ids=["record-100-missing-body", "all-body-sections-empty"],
)
def test_v2_provider_contract_rejects_hollow_report_payloads(payload):
    with pytest.raises(ValidationError):
        FinancialAnalysisV2LLMResponse.model_validate(payload)


@pytest.mark.asyncio
async def test_v2_generation_fails_closed_for_record_100_shape(monkeypatch):
    payload = {
        "asset": "SPCX",
        "overall_sentiment": "Neutral",
        "confidence_score": 50,
    }
    client = SimpleNamespace(generate=AsyncMock(return_value=json.dumps(payload)))

    async def validate_provider_model(_provider_id, _model_name):
        return "ollama", "fixture-model", client

    monkeypatch.setattr(
        "backend.services.ai.ai_service.validate_provider_model",
        validate_provider_model,
    )

    with pytest.raises(AIStructuredOutputError) as exc_info:
        await ollama_service.generate_analysis_v2(
            _request(), provider="ollama", model="fixture-model"
    )

    assert exc_info.value.details["failure_kind"] == "schema_validation"
    assert (
        client.generate.await_count
        == ollama_service.STRUCTURED_GENERATION_MAX_ATTEMPTS
    )


@pytest.mark.asyncio
async def test_complete_v2_provider_fixture_converts_with_populated_trusted_output(
    monkeypatch,
):
    payload = _provider_payload(article_indices=[2, 2, True, 0, -1, 1, 3, "1"])

    provider_result = FinancialAnalysisV2LLMResponse.model_validate(payload)
    _, _, result = await _run_v2(monkeypatch, payload)

    assert provider_result.executive_summary
    assert result.executive_summary
    assert result.news_summary
    assert result.key_catalysts
    assert result.key_risks
    assert result.bull_case
    assert result.bear_case
    assert result.market_reaction_analysis
    assert result.technical_analysis
    assert result.technical_analysis.trend == "Insufficient supplied technical data."
    assert result.technical_analysis.support_levels == []
    assert result.technical_analysis.resistance_levels == []
    assert result.technical_analysis.breakout_level == "N/A"
    assert result.technical_analysis.breakdown_level == "N/A"
    assert result.outlook
    assert result.actionable_insights
    assert result.portfolio_fit
    assert [article.title for article in result.articles_used] == [
        "Trusted second article",
        "Trusted first article",
    ]


@pytest.mark.asyncio
async def test_v2_discards_provider_metadata_and_maps_only_sanitized_trusted_indexes(
    monkeypatch,
):
    _, _, result = await _run_v2(
        monkeypatch,
        _provider_payload(article_indices=[2, 2, True, 0, -1, 1, 3, "1"]),
    )

    assert result.asset == "TEST"
    assert result.current_price_at_analysis == 100.0
    assert result.report_id is None
    assert result.articles_used == [
        ArticleReference(
            title="Trusted second article",
            url="https://trusted.example/second",
            published_at="2026-08-30T11:00:00+00:00",
        ),
        ArticleReference(
            title="Trusted first article",
            url="https://trusted.example/first",
            published_at="2026-08-30T10:00:00+00:00",
        ),
    ]
    serialized = json.dumps(result.model_dump(mode="json"))
    assert "attacker.invalid" not in serialized
    assert "PROVIDER FORGERY" not in serialized
    assert "article_indices_used" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize("indices", [None, [], [True, 0, -1, 99, "1"]])
async def test_v2_without_usable_indexes_uses_all_trusted_supplied_articles(
    monkeypatch, indices
):
    payload = _provider_payload(article_indices=indices)
    _, _, result = await _run_v2(monkeypatch, payload)

    assert [article.url for article in result.articles_used] == [
        "https://trusted.example/first",
        "https://trusted.example/second",
    ]


def test_v2_hash_covers_exact_v2_prompt_and_schema_but_no_v3_review_material():
    request = _request()
    pipeline = ollama_service.get_current_analysis_prompt_pipeline()
    payload = ollama_service._v2_prompt_hash_payload(request)
    decoded = payload.decode("utf-8")

    assert pipeline.prompt_hash(request) == hashlib.sha256(payload).hexdigest()
    assert decoded == (
        f"{ollama_service.PROMPT_V2_SYSTEM_PROMPT}\0"
        f"{ollama_service._build_v2_user_prompt(request)}\0"
        f"{pipeline.structured_output_contract}"
    )
    assert ollama_service.GROUNDING_REVIEW_SYSTEM_PROMPT not in decoded
    assert ollama_service.SEMANTIC_CORRECTION_INSTRUCTION not in decoded
    assert "patch_target_id" not in decoded
    schema = json.loads(pipeline.structured_output_contract)
    assert set(schema["required"]) == V2_PROVIDER_REQUIRED_FIELDS
    assert schema == FinancialAnalysisV2LLMResponse.model_json_schema()
    assert "article_indices_used" in schema["properties"]
    assert "articles_used" not in schema["properties"]
    assert "current_price_at_analysis" not in schema["properties"]
    assert "report_id" not in schema["properties"]
    assert pipeline.prompt_hash(request) != (
        "a4ff3e634bc474104241432dfdc8ef008a0e3c31b26f83d0cdd20b516b3c9de9"
    )


def test_sparse_historical_public_report_remains_backward_compatible():
    historical_payload = {
        "asset": "LEGACY",
        "overall_sentiment": "Neutral",
        "confidence_score": 50,
    }

    public_report = FinancialAnalysisResponse.model_validate(historical_payload)
    api_report = AnalysisReportDetail(
        id=1,
        ticker="LEGACY",
        report_data=historical_payload,
        articles_count=0,
        model_used="historical-model",
        prompt_version="2.0",
        created_at=datetime(2025, 1, 1),
    )

    assert public_report.executive_summary is None
    assert public_report.news_summary == []
    assert public_report.technical_analysis is None
    assert api_report.report_data == historical_payload


def _route_state(monkeypatch, generated):
    article = SimpleNamespace(
        id=1,
        title="Trusted route article",
        summary="Trusted route summary.",
        provider_name="Trusted Route Wire",
        article_url="https://trusted.example/route",
        pub_date=None,
    )

    async def execute(_statement):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: [article])
        )

    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    generate = (
        AsyncMock(side_effect=generated)
        if isinstance(generated, Exception)
        else AsyncMock(return_value=generated)
    )
    selected = ollama_service.get_current_analysis_prompt_pipeline()
    pipeline = SimpleNamespace(
        version=selected.version,
        generate=generate,
        prompt_hash=selected.prompt_hash,
    )
    persist = AsyncMock(return_value=77)
    monkeypatch.setattr(
        analysis_router,
        "get_current_analysis_prompt_pipeline",
        lambda: pipeline,
    )
    monkeypatch.setattr(analysis_router, "create_report", persist)
    monkeypatch.setattr(
        analysis_router,
        "get_hybrid_stock_price",
        AsyncMock(
            return_value={
                "current_price": 100.0,
                "previous_close": 99.0,
                "fifty_two_week_high": None,
                "fifty_two_week_low": None,
                "volume": 1_000_000,
                "company_name": "Test Company",
            }
        ),
    )
    monkeypatch.setattr(
        analysis_router,
        "resolve_provider_model",
        lambda *_args: ("ollama", "fixture-model"),
    )
    monkeypatch.setattr(analysis_router, "_get_timeout_for_model", lambda *_: 30)
    return session, pipeline, generate, persist


async def _call_route(session):
    return await analysis_router.analysis_analyze_ticker(
        ticker="TEST",
        max_articles=1,
        days_back=3,
        model="fixture-model",
        provider="ollama",
        article_ids=[1],
        session=session,
    )


@pytest.mark.asyncio
async def test_successful_v2_route_persists_once_with_coupled_version_and_hash(
    monkeypatch,
):
    accepted = FinancialAnalysisResponse(
        asset="TEST",
        overall_sentiment="Neutral",
        confidence_score=60,
        investment_rating="Hold",
        articles_used=[
            ArticleReference(
                title="Trusted route article",
                url="https://trusted.example/route",
                published_at=None,
            )
        ],
        executive_summary="Accepted deterministic fixture.",
    )
    session, pipeline, generate, persist = _route_state(monkeypatch, accepted)

    result = await _call_route(session)

    assert result.report_id == 77
    generate.assert_awaited_once()
    persist.assert_awaited_once()
    session.commit.assert_awaited_once()
    generated_request = generate.await_args.args[0]
    persisted = persist.await_args.kwargs
    assert persisted["prompt_version"] == pipeline.version == "2.0"
    assert persisted["prompt_hash"] == pipeline.prompt_hash(generated_request)


@pytest.mark.asyncio
async def test_incomplete_structured_v2_route_never_persists_or_commits(monkeypatch):
    failure = AIStructuredOutputError(
        "incomplete provider output",
        details={"failure_kind": "schema_validation", "prompt_version": "2.0"},
    )
    session, _pipeline, generate, persist = _route_state(
        monkeypatch, failure
    )

    with pytest.raises(AIStructuredOutputError, match="incomplete provider output"):
        await _call_route(session)

    generate.assert_awaited_once()
    persist.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_ai_worker_uses_shared_pipeline_selector_and_has_no_version_constant():
    source = (
        ollama_service.__file__.replace("ollama_service.py", "ai_worker.py")
    )
    with open(source, encoding="utf-8-sig") as handle:
        worker_source = handle.read()

    assert "get_current_analysis_prompt_pipeline" in worker_source
    assert "pipeline.version" in worker_source
    assert "CURRENT_PROMPT_VERSION" not in worker_source
