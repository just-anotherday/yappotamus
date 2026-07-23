"""Resumable local orchestration for Article Intelligence maintenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol
from uuid import UUID, uuid4

from backend.intelligence.article_service import ARTICLE_SYSTEM_PROMPT
from backend.intelligence.contracts import (
    ArtifactEvaluation, GenerationAttemptEvaluation, IntelligenceStage, ValidationContext,
)
from backend.intelligence.generation import IntelligenceGenerator
from backend.intelligence.schemas import ArticleIntelligenceOutput
from backend.intelligence.validation import LayeredJSONValidator
from backend.maintenance.article_intelligence.clients import (
    ExportClient, MaintenanceClientError, PromptCompatibilityClient, PublisherClient,
)
from backend.maintenance.article_intelligence.composition import build_maintenance_provider, maintenance_routing_decision
from backend.maintenance.article_intelligence.contracts import (
    ExportArticle, ExportSessionCreate, ImportBatchRequest, ImportCandidate,
)
from backend.maintenance.article_intelligence.run_store import LocalRun, SQLiteMaintenanceRunStore


class MaintenanceGenerator(Protocol):
    async def generate(self, article: ExportArticle, *, model: str, artifact_identity: str) -> tuple[ArticleIntelligenceOutput, dict]: ...


class _NoopEvaluationRecorder:
    async def record_attempt(self, evaluation: GenerationAttemptEvaluation) -> None:
        return None

    async def record_artifact(self, evaluation: ArtifactEvaluation) -> None:
        return None


class OllamaMaintenanceGenerator:
    async def generate(self, article: ExportArticle, *, model: str, artifact_identity: str) -> tuple[ArticleIntelligenceOutput, dict]:
        providers, _ = build_maintenance_provider(model)
        decision = await maintenance_routing_decision(model)
        validator = LayeredJSONValidator(
            ArticleIntelligenceOutput, ("summary", "market_impact", "short_term_outlook", "long_term_outlook"),
        )
        generator = IntelligenceGenerator(providers, validator, _NoopEvaluationRecorder())
        source = {
            "title": article.title, "summary": article.summary, "ticker": article.ticker,
            "url": article.article_url,
            "published_at": article.published_at.isoformat() if article.published_at else None,
        }
        return await generator.generate(
            artifact_type="article", artifact_identity=artifact_identity, decision=decision,
            system_prompt=ARTICLE_SYSTEM_PROMPT,
            user_prompt=f"Analyze this immutable source article and return the complete JSON schema:\n{source}",
            context=ValidationContext(IntelligenceStage.ARTICLE, article.ticker),
        )


@dataclass(frozen=True)
class CoordinatorResult:
    run: LocalRun
    exported: int
    generated: int
    published: int
    rejected: int
    retryable: int


class MaintenanceCoordinator:
    def __init__(self, store: SQLiteMaintenanceRunStore, prompts: PromptCompatibilityClient,
                 exports: ExportClient, publisher: PublisherClient,
                 generator: MaintenanceGenerator | None = None) -> None:
        self.store = store
        self.prompts = prompts
        self.exports = exports
        self.publisher = publisher
        self.generator = generator or OllamaMaintenanceGenerator()

    def create_run(self, *, model: str, client_request_id: UUID | None = None,
                   run_id: UUID | None = None) -> LocalRun:
        return self.store.create_run(run_id or uuid4(), client_request_id or uuid4(), model)

    async def start(self, *, model: str, client_request_id: UUID | None = None,
                    run_id: UUID | None = None, tickers: list[str] | None = None,
                    max_items: int = 25, publish: bool = False,
                    dry_run: bool = False) -> CoordinatorResult:
        run = self.create_run(model=model, client_request_id=client_request_id, run_id=run_id)
        return await self.resume(
            run.run_id, publish=publish, dry_run=dry_run, tickers=tickers, max_items=max_items,
        )

    async def fetch(self, run_id: UUID, *, tickers: list[str] | None = None, max_items: int = 25) -> CoordinatorResult:
        run = self._require(run_id)
        compatibility = await self.prompts.get()
        current = compatibility.current
        if run.prompt_hash and (run.prompt_version != current.version or run.prompt_hash != current.hash):
            raise ValueError("stored run prompt is no longer production-compatible")
        self.store.update_run(
            run_id, state="FETCHING", prompt_version=current.version, prompt_hash=current.hash,
            registry_revision=compatibility.registry_revision, last_error=None,
        )
        if run.batch_id is None:
            envelope = await self.exports.create(ExportSessionCreate(
                client_request_id=run.client_request_id, tickers=tickers or [], max_items=max_items,
            ))
            run = self.store.update_run(run_id, batch_id=UUID(str(envelope["batch_id"])))
        items = self.store.items(run_id)
        if not items:
            exports = await self.exports.items(run.batch_id)
            if any(item.prompt_version != current.version or item.prompt_hash != current.hash for item in exports):
                raise ValueError("export session prompt is not production-compatible")
            self.store.save_exports(run_id, exports)
            if not exports:
                self.store.update_run(run_id, state="COMPLETED", last_error=None)
                return self.status(run_id)
        self.store.update_run(run_id, state="EXPORTED", last_error=None)
        return self.status(run_id)

    async def generate(self, run_id: UUID) -> CoordinatorResult:
        run = self._require(run_id)
        if not run.batch_id or not run.prompt_hash or not run.prompt_version:
            raise ValueError("run must be fetched before generation")
        self.store.update_run(run_id, state="GENERATING", last_error=None)
        for item in self.store.items(run_id):
            if item.candidate is not None or (item.state == "GENERATION_FAILED" and not item.retryable):
                continue
            artifact_id = str(UUID(item.export.input_hash[:32]))
            try:
                output, metadata = await self.generator.generate(
                    item.export, model=run.model, artifact_identity=item.export.input_hash,
                )
                candidate = ImportCandidate(
                    artifact_client_id=UUID(artifact_id),
                    stable_article_identity=item.export.stable_article_identity,
                    ticker=item.export.ticker, source_content_hash=item.export.source_content_hash,
                    prompt_version=item.export.prompt_version, prompt_hash=item.export.prompt_hash,
                    input_hash=item.export.input_hash, export_revision_hint=item.export.revision_hint,
                    provider="ollama", model=run.model, generated_at=datetime.now(timezone.utc),
                    status="completed", output=output, quality_metrics=metadata.get("metrics", {}),
                    evaluation_metadata={
                        "attempt_number": metadata.get("attempt_number"),
                        "duration_ms": metadata.get("duration_ms"),
                        "validation": metadata.get("validation", {}),
                    },
                )
                self.store.save_candidate(run_id, item.ordinal, candidate)
            except Exception as exc:
                retryable = not isinstance(exc, TypeError) and (
                    not isinstance(exc, ValueError) or str(exc).startswith("quality validation exhausted:")
                )
                self.store.save_generation_error(run_id, item.ordinal, str(exc), retryable=retryable)
        state = "READY_TO_PUBLISH" if all(item.candidate for item in self.store.items(run_id)) else "PARTIAL"
        self.store.update_run(run_id, state=state, last_error=None)
        return self.status(run_id)

    async def publish(self, run_id: UUID, *, dry_run: bool = False,
                      client_publish_id: UUID | None = None) -> CoordinatorResult:
        run = self._require(run_id)
        if run.batch_id is None:
            raise ValueError("run must be fetched before publication")
        candidates = [item.candidate for item in self.store.items(run_id)
                      if item.candidate is not None and not item.state.startswith("PUBLISHED_CREATED")
                      and not item.state.startswith("PUBLISHED_ALREADY_EXISTS")]
        if not candidates:
            return self.status(run_id)
        if run.pending_publish_id:
            if run.pending_publish_dry_run != dry_run:
                raise ValueError("an interrupted publication with a different dry-run mode must be resumed first")
            if client_publish_id and client_publish_id != run.pending_publish_id:
                raise ValueError("client_publish_id does not match the interrupted publication")
            publish_id = run.pending_publish_id
        else:
            publish_id = client_publish_id or uuid4()
            self.store.set_pending_publish(run_id, publish_id, dry_run=dry_run)
        self.store.update_run(run_id, state="DRY_RUNNING" if dry_run else "PUBLISHING", last_error=None)
        try:
            outcomes = await self.publisher.publish(ImportBatchRequest(
                batch_id=run.batch_id, client_publish_id=publish_id, artifacts=candidates,
            ), dry_run=dry_run)
        except MaintenanceClientError as exc:
            self.store.update_run(run_id, state="PUBLISH_INTERRUPTED", last_error=str(exc)[:1000])
            raise
        self.store.save_outcomes(run_id, outcomes, dry_run=dry_run)
        self.store.clear_pending_publish(run_id)
        if dry_run:
            state = "READY_TO_PUBLISH"
        else:
            current = self.store.items(run_id)
            state = "COMPLETED" if all(
                item.state in {"PUBLISHED_CREATED", "PUBLISHED_ALREADY_EXISTS"} for item in current
            ) else "PARTIAL"
        self.store.update_run(run_id, state=state, last_error=None)
        return self.status(run_id)

    async def resume(self, run_id: UUID, *, publish: bool = False, dry_run: bool = False,
                     tickers: list[str] | None = None, max_items: int = 25) -> CoordinatorResult:
        run = self._require(run_id)
        if run.state == "COMPLETED" and not self.store.items(run_id):
            return self.status(run_id)
        if run.batch_id is None or not self.store.items(run_id):
            await self.fetch(run_id, tickers=tickers, max_items=max_items)
        if any(item.candidate is None and (item.retryable or item.state == "EXPORTED") for item in self.store.items(run_id)):
            await self.generate(run_id)
        if publish:
            return await self.publish(run_id, dry_run=dry_run)
        return self.status(run_id)

    def status(self, run_id: UUID) -> CoordinatorResult:
        run = self._require(run_id)
        items = self.store.items(run_id)
        return CoordinatorResult(
            run=run, exported=len(items), generated=sum(item.candidate is not None for item in items),
            published=sum(item.state in {"PUBLISHED_CREATED", "PUBLISHED_ALREADY_EXISTS"} for item in items),
            rejected=sum("REJECTED" in item.state or "VALIDATION_FAILED" in item.state for item in items),
            retryable=sum(item.retryable for item in items),
        )

    def _require(self, run_id: UUID) -> LocalRun:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(f"unknown maintenance run: {run_id}")
        return run