"""Production-authoritative export and append-only import services."""

from datetime import datetime, timedelta, timezone
from time import monotonic
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config.settings import settings
from backend.intelligence.article_service import (
    ARTICLE_PROMPT_HASH, ARTICLE_PROMPT_VERSION, article_source_content_hash, article_source_payload,
)
from backend.intelligence.hashing import canonical_hash
from backend.intelligence.contracts import IntelligenceStage, ValidationContext
from backend.intelligence.schemas import ArticleIntelligenceOutput
from backend.intelligence.validation import LayeredJSONValidator
from backend.maintenance.article_intelligence.contracts import (
    ExportArticle, ExportSessionCreate, ImportCandidate, ImportOutcome, StableArticleIdentity,
)
from backend.maintenance.article_intelligence.identity import candidate_fingerprint, normalized_article_url, stable_article_identity
from backend.maintenance.article_intelligence.lifecycle import BatchState, transition_batch
from backend.maintenance.article_intelligence.prompts import (
    PromptCompatibilityRegistry, PromptHashMismatch, REGISTRY_REVISION, UnknownPromptVersion,
)
from backend.maintenance.article_intelligence.revision import PostgreSQLRevisionAllocator
from backend.models.intelligence import ArticleIntelligence
from backend.models.maintenance import (
    ArticleIntelligenceMaintenanceBatch as Batch,
    ArticleIntelligenceMaintenanceExportItem as ExportItem,
    ArticleIntelligenceMaintenanceImportItem as ImportItem,
)
from backend.models.news import NewsArticle


def reconcile_batch(batch: Batch, rows: list[ImportItem]) -> BatchState:
    """Recompute non-dry-run counters; never increment counters from request input."""
    batch.imported_count = sum(row.outcome == "created" for row in rows)
    batch.already_exists_count = sum(row.outcome == "already_exists" for row in rows)
    batch.rejected_count = sum(row.outcome.startswith("rejected_") or row.outcome == "validation_failed" for row in rows)
    batch.hash_mismatch_count = sum("hash_mismatch" in row.outcome for row in rows)
    batch.revision_conflict_count = sum(row.outcome == "rejected_revision_conflict" for row in rows)
    resolved = batch.imported_count + batch.already_exists_count
    return BatchState.COMPLETED if resolved >= batch.exported_count and batch.rejected_count == 0 else BatchState.PARTIAL


def _transport_payload(article: NewsArticle) -> dict:
    payload = article_source_payload(article)
    payload["published_at"] = article.pub_date.isoformat() if article.pub_date else None
    return payload


class MaintenanceExportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, request: ExportSessionCreate) -> Batch:
        existing = (await self.session.execute(select(Batch).where(Batch.client_request_id == request.client_request_id))).scalar_one_or_none()
        if existing:
            return existing
        tickers = tuple(dict.fromkeys(t.strip().upper() for t in request.tickers)) or settings.INTELLIGENCE_PILOT_TICKERS
        if any(not settings.is_intelligence_pilot_ticker(t) for t in tickers):
            raise ValueError("unsupported maintenance ticker")
        batch = Batch(
            client_request_id=request.client_request_id, schema_version=request.schema_version,
            state=BatchState.EXPORTING, requested_tickers=list(tickers), requested_count=request.max_items,
            prompt_version=ARTICLE_PROMPT_VERSION, prompt_hash=ARTICLE_PROMPT_HASH,
            registry_revision=REGISTRY_REVISION, expires_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        self.session.add(batch); await self.session.flush()
        articles = (await self.session.execute(select(NewsArticle).where(
            NewsArticle.ticker.in_(tickers),
        ).order_by(NewsArticle.pub_date.asc().nulls_last(), NewsArticle.id.asc()))).scalars().all()
        ordinal = 0
        for article in articles:
            source_hash = article_source_content_hash(article)
            input_hash = canonical_hash({"source": source_hash, "prompt": ARTICLE_PROMPT_HASH})
            completed = (await self.session.execute(select(ArticleIntelligence.id).where(
                ArticleIntelligence.article_id == article.id,
                ArticleIntelligence.source_content_hash == source_hash,
                ArticleIntelligence.prompt_hash == ARTICLE_PROMPT_HASH,
                ArticleIntelligence.input_hash == input_hash,
                ArticleIntelligence.status == "completed",
            ).limit(1))).scalar_one_or_none()
            if completed:
                continue
            revision_hint = ((await self.session.execute(select(ArticleIntelligence.generation_revision).where(
                ArticleIntelligence.article_id == article.id,
                ArticleIntelligence.source_content_hash == source_hash,
                ArticleIntelligence.prompt_hash == ARTICLE_PROMPT_HASH,
                ArticleIntelligence.input_hash == input_hash,
            ).order_by(ArticleIntelligence.generation_revision.desc()).limit(1))).scalar_one_or_none() or 0) + 1
            identity = stable_article_identity(article)
            self.session.add(ExportItem(
                batch_id=batch.id, ordinal=ordinal, article_id=article.id,
                stable_identity_kind=identity.kind, stable_identity_value=identity.value,
                ticker=article.ticker.upper(), source_payload=_transport_payload(article),
                source_content_hash=source_hash, prompt_version=ARTICLE_PROMPT_VERSION,
                prompt_hash=ARTICLE_PROMPT_HASH, input_hash=input_hash, revision_hint=revision_hint,
            ))
            ordinal += 1
            if ordinal >= request.max_items:
                break
        batch.exported_count = ordinal
        batch.state = transition_batch(BatchState(batch.state), BatchState.GENERATING)
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            existing = (await self.session.execute(select(Batch).where(
                Batch.client_request_id == request.client_request_id
            ))).scalar_one_or_none()
            if existing is None:
                raise
            return existing
        return batch

    async def items(self, batch_id: UUID, offset: int = 0, limit: int = 25) -> list[ExportArticle]:
        rows = (await self.session.execute(select(ExportItem).where(ExportItem.batch_id == batch_id)
            .order_by(ExportItem.ordinal).offset(offset).limit(limit))).scalars().all()
        return [ExportArticle(
            stable_article_identity=StableArticleIdentity(kind=row.stable_identity_kind, value=row.stable_identity_value),
            ticker=row.ticker, title=row.source_payload.get("title", ""), summary=row.source_payload.get("summary", ""),
            article_url=row.source_payload.get("url", ""), published_at=row.source_payload.get("published_at"),
            source_content_hash=row.source_content_hash, prompt_version=row.prompt_version,
            prompt_hash=row.prompt_hash, input_hash=row.input_hash, revision_hint=row.revision_hint,
        ) for row in rows]


class MaintenanceImportService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.registry = PromptCompatibilityRegistry()

    async def _resolve(self, identity: StableArticleIdentity) -> NewsArticle | None:
        if identity.kind == "finnhub_id":
            return (await self.session.execute(select(NewsArticle).where(NewsArticle.finnhub_id == identity.value))).scalar_one_or_none()
        rows = (await self.session.execute(select(NewsArticle).where(NewsArticle.article_url.is_not(None)))).scalars().all()
        return next((row for row in rows if canonical_hash(normalized_article_url(row.article_url)) == identity.value), None)

    @staticmethod
    async def _prior_outcome(session: AsyncSession, prior: ImportItem, *, exact_replay: bool = False) -> ImportOutcome:
        artifact = await session.get(ArticleIntelligence, prior.article_intelligence_id) if prior.article_intelligence_id else None
        return ImportOutcome(
            artifact_client_id=prior.artifact_client_id,
            outcome=prior.outcome if exact_replay or not artifact else "already_exists",
            production_artifact_id=artifact.id if artifact else None,
            generation_revision=artifact.generation_revision if artifact else None,
            candidate_fingerprint=prior.candidate_fingerprint,
            retryable=prior.outcome in {"validation_failed", "rejected_revision_conflict"},
            reason_code=prior.reason_code,
        )

    async def _record(self, batch: Batch, candidate: ImportCandidate, client_publish_id: UUID,
                      publish_request_hash: str, outcome: ImportOutcome, *, dry_run: bool, article_id: int | None,
                      duration_ms: int) -> None:
        prior = (await self.session.execute(select(ImportItem).where(
            ImportItem.batch_id == batch.id,
            ImportItem.artifact_client_id == candidate.artifact_client_id,
            ImportItem.is_dry_run == dry_run,
        ))).scalar_one_or_none()
        if prior:
            prior.client_publish_id = client_publish_id
            prior.publish_request_hash = publish_request_hash
            prior.article_id = article_id
            prior.article_intelligence_id = outcome.production_artifact_id
            prior.candidate_fingerprint = outcome.candidate_fingerprint
            prior.outcome = outcome.outcome
            prior.reason_code = outcome.reason_code
            prior.duration_ms = duration_ms
            prior.client_metrics = candidate.quality_metrics
        else:
            self.session.add(ImportItem(
                batch_id=batch.id, artifact_client_id=candidate.artifact_client_id,
                client_publish_id=client_publish_id, publish_request_hash=publish_request_hash,
                is_dry_run=dry_run, article_id=article_id,
                article_intelligence_id=outcome.production_artifact_id,
                candidate_fingerprint=outcome.candidate_fingerprint, outcome=outcome.outcome,
                reason_code=outcome.reason_code, duration_ms=duration_ms,
                client_metrics=candidate.quality_metrics,
            ))

    async def validate_and_import(self, batch: Batch, candidate: ImportCandidate, *,
                                  client_publish_id: UUID, publish_request_hash: str,
                                  dry_run: bool = False) -> ImportOutcome:
        started = monotonic()
        prior = (await self.session.execute(select(ImportItem).where(
            ImportItem.batch_id == batch.id, ImportItem.artifact_client_id == candidate.artifact_client_id,
            ImportItem.is_dry_run == dry_run,
        ))).scalar_one_or_none()
        if prior and prior.client_publish_id == client_publish_id:
            return await self._prior_outcome(self.session, prior, exact_replay=True)
        if prior and prior.article_intelligence_id:
            return await self._prior_outcome(self.session, prior)
        article = await self._resolve(candidate.stable_article_identity)
        outcome: ImportOutcome
        if article is None:
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="rejected_unknown_article")
            await self._record(batch, candidate, client_publish_id, publish_request_hash, outcome, dry_run=dry_run,
                               article_id=None, duration_ms=int((monotonic() - started) * 1000))
            return outcome
        source_hash = article_source_content_hash(article)
        input_hash = canonical_hash({"source": source_hash, "prompt": ARTICLE_PROMPT_HASH})
        if not settings.is_intelligence_pilot_ticker(article.ticker) or candidate.ticker != article.ticker.strip().upper():
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="rejected_ticker")
        elif candidate.source_content_hash != source_hash:
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="rejected_source_hash_mismatch")
        else:
            try:
                self.registry.require_compatible(candidate.prompt_version, candidate.prompt_hash)
            except UnknownPromptVersion:
                outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="rejected_prompt_version")
            except PromptHashMismatch:
                outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="rejected_prompt_hash_mismatch")
            else:
                outcome = None
        if outcome is None and candidate.input_hash != input_hash:
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="rejected_input_hash_mismatch")
        if outcome is None and candidate.model not in settings.MAINTENANCE_OLLAMA_ALLOWED_MODELS:
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="rejected_model")
        if outcome is None:
            validator = LayeredJSONValidator(ArticleIntelligenceOutput, ("summary", "market_impact", "short_term_outlook", "long_term_outlook"))
            validation = await validator.validate(candidate.output.model_dump_json(), ValidationContext(IntelligenceStage.ARTICLE, article.ticker))
            if not validation.accepted:
                outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="validation_failed",
                                        retryable=any(issue.retryable for issue in validation.issues),
                                        reason_code=validation.issues[0].code if validation.issues else None)
        if outcome is not None:
            await self._record(batch, candidate, client_publish_id, publish_request_hash, outcome, dry_run=dry_run,
                               article_id=article.id, duration_ms=int((monotonic() - started) * 1000))
            return outcome
        fingerprint = candidate_fingerprint(stable_identity=candidate.stable_article_identity,
            source_content_hash=source_hash, prompt_hash=ARTICLE_PROMPT_HASH, input_hash=input_hash,
            provider="ollama", model=candidate.model, output=candidate.output)
        prior_fp = (await self.session.execute(select(ImportItem).where(
            ImportItem.candidate_fingerprint == fingerprint, ImportItem.article_intelligence_id.is_not(None),
        ).limit(1))).scalar_one_or_none()
        if prior_fp:
            artifact = await self.session.get(ArticleIntelligence, prior_fp.article_intelligence_id)
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="already_exists",
                production_artifact_id=artifact.id, generation_revision=artifact.generation_revision,
                candidate_fingerprint=fingerprint)
            await self._record(batch, candidate, client_publish_id, publish_request_hash, outcome, dry_run=dry_run,
                               article_id=article.id, duration_ms=int((monotonic() - started) * 1000))
            return outcome
        if dry_run:
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="created", candidate_fingerprint=fingerprint)
            await self._record(batch, candidate, client_publish_id, publish_request_hash, outcome, dry_run=True,
                               article_id=article.id, duration_ms=int((monotonic() - started) * 1000))
            return outcome
        revision = await PostgreSQLRevisionAllocator(self.session).allocate(article_id=article.id,
            source_content_hash=source_hash, prompt_hash=ARTICLE_PROMPT_HASH, input_hash=input_hash)
        # The revision allocator's transaction advisory lock also serializes the
        # final fingerprint decision across independent maintenance batches.
        prior_fp = (await self.session.execute(select(ImportItem).where(
            ImportItem.candidate_fingerprint == fingerprint, ImportItem.article_intelligence_id.is_not(None),
        ).limit(1))).scalar_one_or_none()
        if prior_fp:
            artifact = await self.session.get(ArticleIntelligence, prior_fp.article_intelligence_id)
            outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="already_exists",
                production_artifact_id=artifact.id, generation_revision=artifact.generation_revision,
                candidate_fingerprint=fingerprint)
            await self._record(batch, candidate, client_publish_id, publish_request_hash, outcome, dry_run=False,
                               article_id=article.id, duration_ms=int((monotonic() - started) * 1000))
            return outcome
        output = candidate.output
        generated_at = candidate.generated_at.astimezone(timezone.utc).replace(tzinfo=None)
        row = ArticleIntelligence(article_id=article.id, ticker=article.ticker, status="completed", provider="ollama",
            model=candidate.model, prompt_version=ARTICLE_PROMPT_VERSION, prompt_hash=ARTICLE_PROMPT_HASH,
            source_content_hash=source_hash, input_hash=input_hash, generation_revision=revision,
            summary_hash=canonical_hash(output.summary), summary=output.summary, sentiment=output.sentiment,
            confidence=output.confidence, importance_score=output.importance_score, market_impact=output.market_impact,
            short_term_outlook=output.short_term_outlook, long_term_outlook=output.long_term_outlook,
            structured_data=output.model_dump(exclude={"summary", "sentiment", "confidence", "importance_score", "market_impact", "short_term_outlook", "long_term_outlook"}),
            routing_metadata={"source": "maintenance_import"}, evaluation_metadata=candidate.evaluation_metadata,
            generated_at=generated_at)
        self.session.add(row); await self.session.flush()
        outcome = ImportOutcome(artifact_client_id=candidate.artifact_client_id, outcome="created",
            production_artifact_id=row.id, generation_revision=revision, candidate_fingerprint=fingerprint)
        await self._record(batch, candidate, client_publish_id, publish_request_hash, outcome, dry_run=False,
                           article_id=article.id, duration_ms=int((monotonic() - started) * 1000))
        return outcome

    async def publish(self, batch_id: UUID, client_publish_id: UUID,
                      candidates: list[ImportCandidate], *, dry_run: bool) -> tuple[Batch, list[ImportOutcome]]:
        batch = (await self.session.execute(select(Batch).where(Batch.id == batch_id).with_for_update())).scalar_one_or_none()
        if batch is None:
            raise LookupError("export session not found")
        if batch.expires_at <= datetime.now(timezone.utc):
            raise ValueError("export session has expired")
        publish_request_hash = canonical_hash({
            "batch_id": str(batch_id), "client_publish_id": str(client_publish_id),
            "dry_run": dry_run,
            "artifacts": [item.model_dump(mode="json") for item in candidates],
        })
        replay = (await self.session.execute(select(ImportItem).where(
            ImportItem.batch_id == batch.id, ImportItem.client_publish_id == client_publish_id,
            ImportItem.is_dry_run == dry_run,
        ).order_by(ImportItem.id))).scalars().all()
        if (len(replay) == len(candidates)
                and {row.artifact_client_id for row in replay} == {item.artifact_client_id for item in candidates}
                and all(row.publish_request_hash == publish_request_hash for row in replay)):
            return batch, [await self._prior_outcome(self.session, row, exact_replay=True) for row in replay]
        if replay:
            raise ValueError("client_publish_id replay payload does not match the original request")
        if not dry_run:
            state = BatchState(batch.state)
            if state == BatchState.GENERATING:
                batch.state = transition_batch(state, BatchState.READY_TO_PUBLISH)
                state = BatchState(batch.state)
            if state in {BatchState.READY_TO_PUBLISH, BatchState.PARTIAL}:
                batch.state = transition_batch(state, BatchState.PUBLISHING)
            elif state == BatchState.COMPLETED:
                raise ValueError("completed batch accepts exact request replays only")
            elif state != BatchState.PUBLISHING:
                raise ValueError(f"batch cannot be published from state {state}")
        outcomes = [await self.validate_and_import(
            batch, item, client_publish_id=client_publish_id,
            publish_request_hash=publish_request_hash, dry_run=dry_run,
        )
                    for item in candidates]
        await self.session.flush()
        if not dry_run:
            rows = (await self.session.execute(select(ImportItem).where(
                ImportItem.batch_id == batch.id, ImportItem.is_dry_run.is_(False)
            ))).scalars().all()
            target = reconcile_batch(batch, rows)
            batch.state = transition_batch(BatchState.PUBLISHING, target)
            batch.completed_at = datetime.now(timezone.utc) if target == BatchState.COMPLETED else None
            # Assign after all query-triggered autoflush points so a concurrent
            # global publication-id conflict is normalized by the commit handler.
            batch.client_publish_id = client_publish_id
        try:
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ValueError("publication conflicted with a concurrent request; retry safely") from None
        return batch, outcomes