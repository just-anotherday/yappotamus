"""Ordered transport, schema, taxonomy, and semantic validation."""

from __future__ import annotations

import json
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from backend.intelligence.contracts import (
    QualityValidationResult,
    ValidationContext,
    ValidationIssue,
)


T = TypeVar("T", bound=BaseModel)


class LayeredJSONValidator(Generic[T]):
    def __init__(self, schema: type[T], required_nonempty: tuple[str, ...] = ()) -> None:
        self._schema = schema
        self._required_nonempty = required_nonempty

    async def validate(self, output: str, context: ValidationContext) -> QualityValidationResult[T]:
        try:
            payload = json.loads(output)
        except (TypeError, json.JSONDecodeError) as exc:
            return self._failure("transport", "invalid_json", str(exc), True)
        try:
            value = self._schema.model_validate(payload)
        except ValidationError as exc:
            return self._failure("schema", "schema_validation", str(exc), True)

        issues: list[ValidationIssue] = []
        sentiment = getattr(value, "sentiment", None)
        if isinstance(sentiment, str):
            normalized = sentiment.strip().lower().replace(" ", "_")
            if normalized != sentiment:
                value = value.model_copy(update={"sentiment": normalized})
                issues.append(ValidationIssue("taxonomy", "sentiment_normalized", "sentiment normalized", False, "sentiment", True))

        missing = [name for name in self._required_nonempty if not getattr(value, name, None)]
        if missing:
            return QualityValidationResult(
                accepted=False,
                issues=tuple(issues) + tuple(
                    ValidationIssue("semantic", "required_empty", "required content is empty", True, name)
                    for name in missing
                ),
            )
        return QualityValidationResult(
            accepted=True,
            value=value,
            issues=tuple(issues),
            metrics={"schema_completeness": 1.0, "required_field_coverage": 1.0},
        )

    @staticmethod
    def _failure(layer: str, code: str, message: str, retryable: bool) -> QualityValidationResult[T]:
        return QualityValidationResult(False, issues=(ValidationIssue(layer, code, message, retryable),))