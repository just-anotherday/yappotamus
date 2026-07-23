"""Durable evaluation recorder, deliberately separate from routing decisions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.contracts import ArtifactEvaluation, GenerationAttemptEvaluation
from backend.models.intelligence import AIGenerationEvaluation, ArticleIntelligence, DailyTickerIntelligence


class DatabaseEvaluationRecorder:
    def __init__(self, session: AsyncSession, prompt_version: str, prompt_hash: str) -> None:
        self._session = session
        self._prompt_version = prompt_version
        self._prompt_hash = prompt_hash

    async def record_attempt(self, evaluation: GenerationAttemptEvaluation) -> None:
        metadata = evaluation.metadata
        self._session.add(AIGenerationEvaluation(
            artifact_type=evaluation.artifact_type,
            artifact_identity=evaluation.artifact_identity,
            artifact_id=metadata.get("artifact_id"),
            attempt_number=metadata["attempt_number"],
            provider=evaluation.provider,
            model=evaluation.model,
            prompt_version=self._prompt_version,
            prompt_hash=self._prompt_hash,
            routing_metadata=metadata.get("routing", {}),
            validation_metadata=metadata.get("validation", {}),
            metrics=metadata.get("metrics", {}),
            succeeded=evaluation.succeeded,
            fallback_index=metadata.get("fallback_index", 0),
            duration_ms=metadata.get("duration_ms"),
        ))

    async def record_artifact(self, evaluation: ArtifactEvaluation) -> None:
        """Attach aggregate metrics only to the in-transaction artifact being generated."""
        if evaluation.artifact_id <= 0:
            return
        model = {"article": ArticleIntelligence, "daily": DailyTickerIntelligence}.get(evaluation.artifact_type)
        if model is None:
            return
        artifact = (await self._session.execute(
            select(model).where(model.id == evaluation.artifact_id)
        )).scalar_one_or_none()
        if artifact is not None:
            artifact.evaluation_metadata = dict(evaluation.metrics)