"""Ollama Provider - Local LLM via the non-streaming /api/generate API."""

import logging
from typing import Any, Dict, Optional

import httpx

from backend.config.settings import settings
from backend.services.ai.ai_service import BaseAIClient
from backend.services.ai.exceptions import (
    AIConnectionError,
    AIHTTPError,
    AIResponseEnvelopeError,
    AIValidationError,
)

logger = logging.getLogger(__name__)


class OllamaProvider(BaseAIClient):
    """Ollama LLM provider using the /api/generate endpoint."""

    def __init__(self) -> None:
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL

    def default_timeout(self) -> float:
        """Ollama uses model-size-based timeouts, base default for small models."""
        return settings.OLLAMA_TIMEOUT_SMALL_S

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
        """Generate text using Ollama /api/generate endpoint."""
        # Use provided model override, fall back to configured default
        active_model = model or self.model
        payload: Dict[str, Any] = {
            "model": active_model,
            "prompt": user_prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_ctx": 16384,
            },
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        response_schema = kwargs.get("response_schema")
        if response_schema is not None:
            if not isinstance(response_schema, dict):
                raise AIValidationError("Ollama response_schema must be a JSON Schema object")
            # Ollama /api/generate accepts a JSON Schema object in `format` and
            # constrains compatible models to emit a matching JSON object.
            payload["format"] = response_schema
            # Reasoning-capable models can otherwise return their work in
            # `thinking` while leaving the required `/api/generate` `response`
            # field empty. Structured reports need only the final JSON object.
            payload["think"] = False
            payload["options"]["temperature"] = 0

        timeout_s = _get_timeout_for_model(active_model)
        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                resp = await client.post(f"{self.base_url}/api/generate", json=payload)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise AIConnectionError(
                "Ollama is unavailable or timed out during generation",
                details={"provider": "ollama", "exception_type": type(exc).__name__},
            ) from exc

        if resp.status_code != 200:
            raise AIHTTPError(
                "Ollama returned an unsuccessful response during generation",
                details={"provider": "ollama", "status_code": resp.status_code},
            )

        try:
            data = resp.json()
        except ValueError as exc:
            _log_envelope_metadata(resp, None)
            raise AIResponseEnvelopeError(
                "Ollama returned an invalid JSON response envelope",
                details={"failure_kind": "invalid_response_envelope"},
            ) from exc

        _log_envelope_metadata(resp, data)
        if not isinstance(data, dict):
            raise AIResponseEnvelopeError(
                "Ollama returned an invalid response envelope",
                details={"failure_kind": "invalid_response_envelope"},
            )
        if "response" not in data or not isinstance(data["response"], str):
            raise AIResponseEnvelopeError(
                "Ollama response envelope did not contain a string response field",
                details={"failure_kind": "invalid_response_envelope"},
            )
        response_text = data["response"].strip()
        if not response_text:
            raise AIResponseEnvelopeError(
                "Ollama returned an empty generated response",
                details={
                    "failure_kind": "empty_generated_response",
                    "thinking_present": isinstance(data.get("thinking"), str),
                },
            )
        return response_text

    async def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    async def list_models(self) -> list[dict]:
        """Dynamically fetch all installed Ollama models."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                if resp.status_code != 200:
                    return []
                data = resp.json()
                models = []
                for m in data.get("models", []):
                    models.append({
                        "name": m.get("name", "unknown"),
                        "size": m.get("size", 0),
                        "modified_at": m.get("modified_at"),
                    })
                return models
        except Exception as e:
            logger.warning(f"[AI][Ollama] Could not list models: {e}")
            return []


# ----------------------------------------------------------------------
# Helper: timeout selection based on model size (reused from ollama_service.py)
# ----------------------------------------------------------------------

def _get_timeout_for_model(model_name: str) -> float:
    """Return appropriate timeout for the given Ollama model."""
    # Large models (> 8GB) get longer timeouts
    if any(big in model_name.lower() for big in ("70b", "13b", "34b", "65b")):
        return settings.OLLAMA_TIMEOUT_LARGE_S
    return settings.OLLAMA_TIMEOUT_SMALL_S


def _log_envelope_metadata(response: httpx.Response, data: Any) -> None:
    """Log safe `/api/generate` envelope metadata without generated content."""
    headers = getattr(response, "headers", {}) or {}
    if isinstance(data, dict):
        keys = ",".join(sorted(str(key) for key in data))
        response_value = data.get("response")
        thinking_value = data.get("thinking")
        response_present = "response" in data
        thinking_present = "thinking" in data
        response_type = type(response_value).__name__ if response_present else "missing"
        thinking_type = type(thinking_value).__name__ if thinking_present else "missing"
        response_len = len(response_value) if isinstance(response_value, str) else -1
        thinking_len = len(thinking_value) if isinstance(thinking_value, str) else -1
        done = data.get("done")
        done_reason = data.get("done_reason")
    else:
        keys = ""
        response_present = thinking_present = False
        response_type = thinking_type = "missing"
        response_len = thinking_len = -1
        done = done_reason = None

    logger.info(
        "[AI][Ollama] status=%s content_type=%s keys=%s done=%s "
        "done_reason=%s response_present=%s response_type=%s response_len=%d "
        "thinking_present=%s thinking_type=%s thinking_len=%d",
        response.status_code,
        headers.get("content-type", headers.get("Content-Type", "")),
        keys,
        done,
        done_reason,
        response_present,
        response_type,
        response_len,
        thinking_present,
        thinking_type,
        thinking_len,
    )
