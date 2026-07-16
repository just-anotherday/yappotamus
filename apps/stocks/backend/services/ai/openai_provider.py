"""OpenAI Provider - Production LLM via OpenAI Chat Completions API

Implements BaseAIClient interface using the standard OpenAI /v1/chat/completions endpoint.
Reuses the same pattern as the website AI generator (gpt-4o-mini default).

Env vars:
    OPENAI_API_KEY - Required for this provider
    OPENAI_MODEL   - Model name (default: gpt-4o-mini)
"""

import logging
import os
from typing import Any, Dict, Optional

import httpx

from backend.services.ai.ai_service import BaseAIClient

logger = logging.getLogger(__name__)

# --- Configuration ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


class OpenAIProvider(BaseAIClient):
    """OpenAI LLM provider using Chat Completions API."""

    def __init__(self) -> None:
        self.api_key = OPENAI_API_KEY
        self.model = OPENAI_MODEL

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
        """Generate text using OpenAI chat completions."""
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not set")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_error = None
        for attempt in range(1, 4):
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
                    "[AI][OpenAI] Generate attempt %d/3 failed: %s",
                    attempt, exc,
                )

        raise RuntimeError(
            f"OpenAI generate failed after 3 retries: {last_error}"
        ) from last_error

    async def is_available(self) -> bool:
        """Check if OpenAI API key is configured and reachable."""
        if not self.api_key:
            return False
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code == 200
        except Exception:
            return False
