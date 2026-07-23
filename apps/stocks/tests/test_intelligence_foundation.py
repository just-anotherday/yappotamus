"""Deterministic intelligence boundary, routing, validation, and schema tests."""

from pydantic import BaseModel, Field
import pytest

from backend.config.settings import Settings
from backend.intelligence.contracts import (
    ArtifactEvaluation,
    GenerationAttemptEvaluation,
    IntelligenceStage,
    ProviderResult,
    QualityValidationResult,
    RouteTarget,
    RoutingDecision,
    RoutingRequest,
    ValidationContext,
)
from backend.intelligence.generation import IntelligenceGenerator
from backend.intelligence.routing import DeterministicRoutingPolicy, RoutingProfile
from backend.intelligence.validation import LayeredJSONValidator
from backend.models.intelligence import ArticleIntelligence, DailyTickerIntelligence


class ExampleOutput(BaseModel):
    summary: str
    sentiment: str
    confidence: int = Field(ge=1, le=10)


def _policy() -> DeterministicRoutingPolicy:
    local = RouteTarget("ollama", "local-model")
    premium = RouteTarget("openai", "premium-model")
    return DeterministicRoutingPolicy(
        profiles={
            "hybrid": RoutingProfile("hybrid", local, premium, (local,), 8_000),
        },
        configuration_revision="env:test-v1",
        allowed_overrides={"openai": frozenset({"premium-model"})},
    )


@pytest.mark.asyncio
async def test_routing_is_deterministic_and_records_reasons():
    request = RoutingRequest(IntelligenceStage.ARTICLE, estimated_tokens=9_000, deployment_profile="hybrid")
    first = await _policy().decide(request)
    second = await _policy().decide(request)
    assert first == second
    assert first.rule_id == "material-or-large-input"
    assert first.target.provider == "openai"
    assert first.configuration_revision == "env:test-v1"


@pytest.mark.asyncio
async def test_routing_override_is_allowlisted():
    decision = await _policy().decide(RoutingRequest(
        IntelligenceStage.DAILY,
        estimated_tokens=100,
        deployment_profile="hybrid",
        provider_override="openai",
        model_override="premium-model",
    ))
    assert decision.rule_id == "authenticated-override"
    with pytest.raises(ValueError, match="allowlisted"):
        await _policy().decide(RoutingRequest(
            IntelligenceStage.DAILY, 100, deployment_profile="hybrid",
            provider_override="openai", model_override="unknown",
        ))


@pytest.mark.asyncio
async def test_validator_reports_ordered_layers_and_normalizes_taxonomy():
    validator = LayeredJSONValidator(ExampleOutput, required_nonempty=("summary",))
    transport = await validator.validate("not-json", ValidationContext(IntelligenceStage.ARTICLE))
    assert transport.issues[0].layer == "transport"
    schema = await validator.validate('{"summary":"x"}', ValidationContext(IntelligenceStage.ARTICLE))
    assert schema.issues[0].layer == "schema"
    semantic = await validator.validate(
        '{"summary":"","sentiment":"Very Bullish","confidence":8}',
        ValidationContext(IntelligenceStage.ARTICLE),
    )
    assert semantic.issues[-1].layer == "semantic"
    accepted = await validator.validate(
        '{"summary":"Material update","sentiment":"Very Bullish","confidence":8}',
        ValidationContext(IntelligenceStage.ARTICLE),
    )
    assert accepted.accepted
    assert accepted.value.sentiment == "very_bullish"
    assert accepted.issues[0].layer == "taxonomy"


def test_generation_identity_constraints_are_complete_and_append_only():
    article_unique = {constraint.name for constraint in ArticleIntelligence.__table__.constraints}
    daily_unique = {constraint.name for constraint in DailyTickerIntelligence.__table__.constraints}
    assert "uq_article_intelligence_generation" in article_unique
    assert "uq_daily_ticker_intelligence_revision" in daily_unique
    assert "uq_daily_ticker_intelligence_generation" in daily_unique
    assert "is_current" not in DailyTickerIntelligence.__table__.columns
    article_constraint = next(
        constraint for constraint in ArticleIntelligence.__table__.constraints
        if constraint.name == "uq_article_intelligence_generation"
    )
    assert [column.name for column in article_constraint.columns] == [
        "article_id", "source_content_hash", "prompt_hash", "input_hash", "generation_revision",
    ]


def test_pilot_tickers_are_normalized_deduplicated_and_cached(monkeypatch):
    monkeypatch.setenv("INTELLIGENCE_PILOT_TICKERS", " spy, QQQ,spy,IWM ")
    configured = Settings()
    assert configured.INTELLIGENCE_PILOT_TICKERS == ("SPY", "QQQ", "IWM")
    monkeypatch.setenv("INTELLIGENCE_PILOT_TICKERS", "DIA")
    assert configured.INTELLIGENCE_PILOT_TICKERS == ("SPY", "QQQ", "IWM")
    assert configured.is_intelligence_pilot_ticker(" qqq ")
    assert not configured.is_intelligence_pilot_ticker("AAPL")


@pytest.mark.parametrize("value", ["", "SPY,$BAD", "WHITE SPACE"])
def test_pilot_tickers_reject_invalid_configuration(monkeypatch, value):
    monkeypatch.setenv("INTELLIGENCE_PILOT_TICKERS", value)
    with pytest.raises(EnvironmentError):
        Settings().INTELLIGENCE_PILOT_TICKERS


class _Provider:
    def __init__(self, name, outcomes):
        self.provider_name = name
        self.outcomes = iter(outcomes)

    async def generate(self, request):
        outcome = next(self.outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return ProviderResult(outcome, self.provider_name, request.model, 7)


class _Validator:
    async def validate(self, output, context):
        return QualityValidationResult(True, ExampleOutput(summary=output, sentiment="neutral", confidence=7), metrics={"quality": 1})


class _Recorder:
    def __init__(self):
        self.attempts = []
        self.artifacts = []

    async def record_attempt(self, evaluation: GenerationAttemptEvaluation):
        self.attempts.append(evaluation)

    async def record_artifact(self, evaluation: ArtifactEvaluation):
        self.artifacts.append(evaluation)


@pytest.mark.asyncio
async def test_provider_errors_are_recorded_retried_and_fall_back():
    recorder = _Recorder()
    generator = IntelligenceGenerator(
        {
            "local": _Provider("local", [RuntimeError("offline"), RuntimeError("offline")]),
            "premium": _Provider("premium", ["accepted"]),
        },
        _Validator(),
        recorder,
    )
    decision = RoutingDecision(
        target=RouteTarget("local", "local-model"), rule_id="test", deployment_profile="hybrid",
        configuration_revision="test:v1", reasons=("test",), fallback_chain=(RouteTarget("premium", "premium-model"),),
    )
    value, metadata = await generator.generate(
        artifact_type="article", artifact_identity="identity", artifact_id=42, decision=decision,
        system_prompt="system", user_prompt="user", context=ValidationContext(IntelligenceStage.ARTICLE),
    )
    assert value.summary == "accepted"
    assert metadata["provider"] == "premium"
    assert [attempt.succeeded for attempt in recorder.attempts] == [False, False, True]
    assert recorder.attempts[0].metadata["validation"]["issues"][0]["layer"] == "provider"
    assert recorder.artifacts[0].artifact_id == 42
    assert recorder.artifacts[0].metrics["attempt_count"] == 3
    assert recorder.artifacts[0].metrics["fallback_index"] == 1