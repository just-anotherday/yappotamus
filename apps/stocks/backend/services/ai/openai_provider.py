"""OpenAI Provider - Production LLM via OpenAI Chat Completions API

Implements BaseAIClient interface using the standard OpenAI /v1/chat/completions endpoint.
Reuses the same pattern as the website AI generator (gpt-4o-mini default).

Env vars:
    OPENAI_API_KEY - Required for this provider
    OPENAI_MODEL   - Model name (default: gpt-4o-mini)
"""

import logging
from typing import Any, Dict, Optional

import httpx

from backend.config.settings import settings
from backend.services.ai.ai_service import BaseAIClient
from backend.services.ai.exceptions import AIConnectionError, AIValidationError

logger = logging.getLogger(__name__)


class OpenAIProvider(BaseAIClient):
    """OpenAI LLM provider using Chat Completions API."""

    def __init__(self) -> None:
        self.api_key = settings.OPENAI_API_KEY or ""
        self.model = settings.OPENAI_MODEL

    def default_timeout(self) -> float:
        """OpenAI has a fixed short timeout."""
        return 120.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Generate text using OpenAI chat completions."""
        if not self.api_key:
            raise AIValidationError("OPENAI_API_KEY is not set")

        max_attempts = kwargs.get("max_attempts", 3)
        if (
            isinstance(max_attempts, bool)
            or not isinstance(max_attempts, int)
            or not 1 <= max_attempts <= 3
        ):
            raise AIValidationError("OpenAI max_attempts must be an integer from 1 to 3")

        # Use provided model override, fall back to configured default
        active_model = model or self.model

        # Cost control: never call OpenAI with a model outside the allowlist,
        # even if a caller bypasses the upstream validation in ollama_service.
        allowed = settings.OPENAI_ALLOWED_MODELS
        if active_model not in allowed:
            raise AIValidationError(f"Model {active_model} is not allowed")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload: Dict[str, Any] = {
            "model": active_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        response_schema = kwargs.get("response_schema")
        if response_schema is not None:
            if not isinstance(response_schema, dict):
                raise AIValidationError(
                    "OpenAI response_schema must be a JSON Schema object"
                )
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    # Generic callers may provide valid JSON Schema features
                    # outside OpenAI's smaller strict-schema subset. The
                    # service layer still performs authoritative Pydantic
                    # validation on every structured response.
                    "strict": False,
                    "schema": response_schema,
                },
            }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(1, max_attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        json=payload,
                        headers=headers,
                    )
                    if resp.status_code != 200:
                        error_data = resp.json() if resp.text else {}
                        raise httpx.HTTPStatusError(
                            f"OpenAI returned {resp.status_code}: {error_data}",
                            request=resp.request,
                            response=resp,
                        )
                    data = resp.json()
                    return (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                        .strip()
                    )
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[AI][OpenAI] Generate attempt %d/%d failed: %s",
                    attempt, max_attempts, exc,
                )

        raise AIConnectionError(
            f"OpenAI generate failed after {max_attempts} attempt(s): {last_error}"
        ) from last_error

    async def is_available(self) -> bool:
        """Return whether required local OpenAI configuration is present.

        Avoid a billable/unrestricted provider discovery request. Connectivity is
        established by the actual generation call and mapped to AIConnectionError.
        """
        return bool(self.api_key and settings.OPENAI_ALLOWED_MODELS)

    async def list_models(self) -> list[dict]:
        """Return allowed OpenAI models.

        Only returns models from OPENAI_ALLOWED_MODELS whitelist.
        Never exposes unrestricted model discovery to the frontend for cost control.
        """
        allowed = settings.OPENAI_ALLOWED_MODELS
        return [
            {"name": model, "size": 0, "modified_at": None}
            for model in allowed
        ]
