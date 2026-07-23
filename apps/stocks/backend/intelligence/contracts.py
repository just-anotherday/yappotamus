"""Architectural boundary contracts and transport objects for intelligence generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, Protocol, TypeVar


class IntelligenceStage(StrEnum):
    ARTICLE = "article"
    DAILY = "daily"
    INVESTMENT_REPORT = "investment_report"


@dataclass(frozen=True)
class RoutingRequest:
    stage: IntelligenceStage
    estimated_tokens: int
    article_count: int = 1
    has_earnings: bool = False
    has_sec_content: bool = False
    retry_count: int = 0
    prior_validation_failures: int = 0
    deployment_profile: str = "local-only"
    provider_override: str | None = None
    model_override: str | None = None


@dataclass(frozen=True)
class RouteTarget:
    provider: str
    model: str


@dataclass(frozen=True)
class RoutingDecision:
    target: RouteTarget
    rule_id: str
    deployment_profile: str
    configuration_revision: str
    reasons: tuple[str, ...]
    fallback_chain: tuple[RouteTarget, ...] = ()


@dataclass(frozen=True)
class GenerationRequest:
    model: str
    system_prompt: str
    user_prompt: str
    temperature: float = 0.2
    max_tokens: int | None = None


@dataclass(frozen=True)
class ProviderResult:
    content: str
    provider: str
    model: str
    duration_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    token_source: str = "estimated"


class AIProvider(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def generate(self, request: GenerationRequest) -> ProviderResult: ...


class RoutingPolicy(Protocol):
    async def decide(self, request: RoutingRequest) -> RoutingDecision: ...


@dataclass(frozen=True)
class ValidationContext:
    stage: IntelligenceStage
    ticker: str | None = None


@dataclass(frozen=True)
class ValidationIssue:
    layer: str
    code: str
    message: str
    retryable: bool
    field: str | None = None
    corrected: bool = False


T = TypeVar("T")


@dataclass(frozen=True)
class QualityValidationResult(Generic[T]):
    accepted: bool
    value: T | None = None
    issues: tuple[ValidationIssue, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)


class QualityValidator(Protocol, Generic[T]):
    async def validate(self, output: str, context: ValidationContext) -> QualityValidationResult[T]: ...


@dataclass(frozen=True)
class GenerationAttemptEvaluation:
    artifact_type: str
    artifact_identity: str
    provider: str
    model: str
    succeeded: bool
    metadata: dict[str, Any]


@dataclass(frozen=True)
class ArtifactEvaluation:
    artifact_type: str
    artifact_id: int
    metrics: dict[str, Any]


class EvaluationRecorder(Protocol):
    async def record_attempt(self, evaluation: GenerationAttemptEvaluation) -> None: ...

    async def record_artifact(self, evaluation: ArtifactEvaluation) -> None: ...


@dataclass(frozen=True)
class ContextBuildRequest:
    ticker: str
    start_date: str | None = None
    end_date: str | None = None
    article_limit: int = 15
    character_budget: int = 50_000
    provider: str | None = None
    model: str | None = None


@dataclass(frozen=True)
class ReportContext:
    text: str
    provenance: tuple[dict[str, Any], ...]
    used_daily_intelligence: bool
    estimated_tokens: int


class ContextBuilder(Protocol):
    async def build(self, request: ContextBuildRequest) -> ReportContext: ...