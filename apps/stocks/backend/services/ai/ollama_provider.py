"""Ollama Provider - Local LLM via Ollama API

Implements BaseAIClient interface for the /api/generate endpoint.
Preserves all existing timeout, retry, and model-size logic from ollama_service.py.
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx

from backend.services.ai.ai_service import BaseAIClient

logger = logging.getLogger(__name__)

# --- Configuration (same env vars as before) ---
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_TIMEOUT_SMALL_S = float(os.getenv("OLLAMA_TIMEOUT_SMALL_S", "900"))
OLLAMA_TIMEOUT_LARGE_S = float(os.getenv("OLLAMA_TIMEOUT_LARGE_S", "1200"))
OLLAMA_MAX_RETRIES = int(os.getenv("OLLAMA_MAX_RETRIES", "3"))
MODEL_SIZE_THRESHOLD_GB = float(os.getenv("MODEL_SIZE_THRESHOLD_GB", "8"))


class OllamaProvider(BaseAIClient):
    """Ollama LLM provider using the /api/generate endpoint."""

    def __init__(self) -> None:
        self.base_url = OLLAMA_BASE_URL
        self.model = OLLAMA_MODEL
        self.max_retries = OLLAMA_MAX_RETRIES

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Generate text using Ollama /api/generate endpoint."""
        payload: Dict[str, Any] = {
            "model": self.model,
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

        timeout_s = _get_timeout_for_model(self.model)

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout_s) as client:
                    resp = await client.post(
                        f"{self.base_url}/api/generate", json=payload
                    )
                    if resp.status_code != 200:
                        raise httpx.HTTPStatusError(
                            f"Ollama returned {resp.status_code}",
                            request=resp.request,
                            response=resp,
                        )
                    data = resp.json()
                    return data.get("response", "").strip()
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[AI][Ollama] Generate attempt %d/%d failed: %s",
                    attempt, self.max_retries, exc,
                )

        raise RuntimeError(f"Ollama generate failed after {self.max_retries} retries: {last_error}") from last_error

    async def is_available(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False


# ----------------------------------------------------------------------
# Helper: timeout selection based on model size (reused from ollama_service.py)
# ----------------------------------------------------------------------

def _get_timeout_for_model(model_name: str) -> float:
    """Return appropriate timeout for the given Ollama model."""
    # Large models (> 8GB) get longer timeouts
    if any(big in model_name.lower() for big in ("70b", "13b", "34b", "65b")):
        return OLLAMA_TIMEOUT_LARGE_S
    return OLLAMA_TIMEOUT_SMALL_S
