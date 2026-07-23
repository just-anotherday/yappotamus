"""Provider-neutral generation loop with validation-gated retry and fallback."""

from dataclasses import asdict
from typing import Generic, TypeVar

from pydantic import BaseModel

from backend.intelligence.contracts import (
    AIProvider, ArtifactEvaluation, EvaluationRecorder, GenerationAttemptEvaluation, GenerationRequest,
    QualityValidator, RoutingDecision, ValidationContext,
)


T = TypeVar("T", bound=BaseModel)


class IntelligenceGenerator(Generic[T]):
    def __init__(self, providers: dict[str, AIProvider], validator: QualityValidator[T], evaluator: EvaluationRecorder) -> None:
        self._providers = providers
        self._validator = validator
        self._evaluator = evaluator

    async def generate(
        self, *, artifact_type: str, artifact_identity: str, artifact_id: int | None = None, decision: RoutingDecision,
        system_prompt: str, user_prompt: str, context: ValidationContext, retries_per_target: int = 2,
    ) -> tuple[T, dict]:
        targets = (decision.target,) + decision.fallback_chain
        attempt_number = 0
        all_issues: list[dict] = []
        for fallback_index, target in enumerate(targets):
            provider = self._providers.get(target.provider)
            if provider is None:
                raise ValueError(f"routed provider is not registered: {target.provider}")
            for _ in range(retries_per_target):
                attempt_number += 1
                try:
                    result = await provider.generate(GenerationRequest(target.model, system_prompt, user_prompt))
                except Exception as exc:
                    issue = {
                        "layer": "provider", "code": type(exc).__name__,
                        "message": str(exc)[:2000], "retryable": True,
                    }
                    all_issues.append(issue)
                    await self._evaluator.record_attempt(GenerationAttemptEvaluation(
                        artifact_type, artifact_identity, target.provider, target.model, False, {
                            "artifact_id": artifact_id, "attempt_number": attempt_number,
                            "fallback_index": fallback_index, "duration_ms": None,
                            "routing": asdict(decision),
                            "validation": {"accepted": False, "issues": [issue]},
                            "metrics": {"provider_error": True},
                        },
                    ))
                    continue
                validation = await self._validator.validate(result.content, context)
                issues = [asdict(issue) for issue in validation.issues]
                all_issues.extend(issues)
                metadata = {
                    "artifact_id": artifact_id, "attempt_number": attempt_number, "fallback_index": fallback_index,
                    "duration_ms": result.duration_ms, "routing": asdict(decision),
                    "validation": {"accepted": validation.accepted, "issues": issues},
                    "metrics": validation.metrics,
                }
                await self._evaluator.record_attempt(GenerationAttemptEvaluation(
                    artifact_type, artifact_identity, result.provider, result.model, validation.accepted, metadata,
                ))
                if validation.accepted and validation.value is not None:
                    await self._evaluator.record_artifact(ArtifactEvaluation(
                        artifact_type=artifact_type,
                        artifact_id=artifact_id or 0,
                        metrics={
                            **validation.metrics, "attempt_count": attempt_number,
                            "fallback_index": fallback_index, "provider": result.provider,
                            "model": result.model,
                        },
                    ))
                    return validation.value, {**metadata, "provider": result.provider, "model": result.model}
                if validation.issues and not any(issue.retryable for issue in validation.issues):
                    break
        raise ValueError(f"quality validation exhausted: {all_issues}")