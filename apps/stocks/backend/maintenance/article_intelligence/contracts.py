"""Strict versioned transport contracts for maintenance publishing."""

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from backend.intelligence.schemas import ArticleIntelligenceOutput


SCHEMA_VERSION = "article-intelligence-maintenance.v1"
SchemaVersion = Literal["article-intelligence-maintenance.v1"]
Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Ticker = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9.-]{0,19}$")]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StableArticleIdentity(StrictContract):
    kind: Literal["finnhub_id", "article_url_hash"]
    value: Annotated[str, StringConstraints(min_length=1, max_length=512)]
    identity_version: Literal["v1"] = "v1"


class ExportSessionCreate(StrictContract):
    schema_version: SchemaVersion = SCHEMA_VERSION
    client_request_id: UUID
    tickers: list[Ticker] = Field(default_factory=list, max_length=20)
    max_items: int = Field(default=25, ge=1, le=50)


class ExportArticle(StrictContract):
    stable_article_identity: StableArticleIdentity
    ticker: Ticker
    title: str = Field(max_length=10_000)
    summary: str = Field(max_length=50_000)
    article_url: str = Field(max_length=4_096)
    published_at: datetime | None = None
    source_content_hash: Sha256
    prompt_version: str = Field(min_length=1, max_length=40)
    prompt_hash: Sha256
    input_hash: Sha256
    revision_hint: int = Field(ge=1)


class ExportSessionEnvelope(StrictContract):
    schema_version: SchemaVersion = SCHEMA_VERSION
    batch_id: UUID
    created_at: datetime
    items: list[ExportArticle] = Field(default_factory=list, max_length=50)
    next_cursor: str | None = Field(default=None, max_length=1_024)


class ImportCandidate(StrictContract):
    """Untrusted candidate; production owns identity and final revision allocation."""

    artifact_client_id: UUID
    stable_article_identity: StableArticleIdentity
    ticker: Ticker
    source_content_hash: Sha256
    prompt_version: str = Field(min_length=1, max_length=40)
    prompt_hash: Sha256
    input_hash: Sha256
    export_revision_hint: int | None = Field(default=None, ge=1)
    provider: Literal["ollama"]
    model: str = Field(min_length=1, max_length=100)
    generated_at: datetime
    status: Literal["completed"]
    output: ArticleIntelligenceOutput
    quality_metrics: dict[str, Any] = Field(default_factory=dict, max_length=50)
    evaluation_metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)


class ImportBatchRequest(StrictContract):
    schema_version: SchemaVersion = SCHEMA_VERSION
    batch_id: UUID
    client_publish_id: UUID
    artifacts: list[ImportCandidate] = Field(min_length=1, max_length=25)


ImportOutcomeCode = Literal[
    "created", "already_exists", "rejected_source_hash_mismatch",
    "rejected_prompt_hash_mismatch", "rejected_input_hash_mismatch",
    "rejected_unknown_article", "rejected_prompt_version",
    "rejected_revision_conflict", "validation_failed", "rejected_ticker",
    "rejected_provider", "rejected_model",
]


class ImportOutcome(StrictContract):
    artifact_client_id: UUID
    outcome: ImportOutcomeCode
    production_artifact_id: int | None = None
    generation_revision: int | None = Field(default=None, ge=1)
    candidate_fingerprint: Sha256 | None = None
    retryable: bool = False
    reason_code: str | None = Field(default=None, max_length=100)