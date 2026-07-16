"""AI Service - Unified interface for all LLM providers

Selects the provider based on AI_PROVIDER environment variable:
  AI_PROVIDER=ollama  -> OllamaProvider (default, local dev)
  AI_PROVIDER=openai  -> OpenAIProvider (production)

To add a new provider:
  1. Create backend/services/ai/<name>_provider.py
  2. Implement BaseAIClient interface
  3. Add the provider name to _PROVIDERS dict below
"""

import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseAIClient(ABC):
    """Abstract base class that all AI providers must implement."""

    @abstractmethod
    async def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> str:
        """Generate a text response from the LLM."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is reachable and configured."""
        ...


def _get_provider() -> BaseAIClient:
    """Factory: instantiate the correct provider based on AI_PROVIDER env var."""
    provider_name = (os.getenv("AI_PROVIDER") or "ollama").strip().lower()

    if provider_name == "openai":
        from backend.services.ai.openai_provider import OpenAIProvider
        logger.info("[AI] Using OpenAI provider")
        return OpenAIProvider()

    # Default: Ollama (local development)
    from backend.services.ai.ollama_provider import OllamaProvider
    if provider_name in ("ollama", ""):
        logger.info("[AI] Using Ollama provider (default)")
        return OllamaProvider()

    raise ValueError(
        f"Unknown AI_PROVIDER='{provider_name}'. "
        f"Supported: ollama, openai"
    )


# Module-level singleton (lazy-initialized on first call)
_ai_service: Optional[BaseAIClient] = None


def get_ai_service() -> BaseAIClient:
    """Return the globally configured AI service instance."""
    global _ai_service
    if _ai_service is None:
        _ai_service = _get_provider()
    return _ai_service


def reset_ai_service():
    """Reset singleton (useful for testing)."""
    global _ai_service
    _ai_service = None
