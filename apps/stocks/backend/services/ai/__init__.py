"""AI Provider Abstraction Layer

Provides a unified interface for calling different LLM providers (Ollama, OpenAI, etc.)
without changing calling code. Selection is controlled via AI_PROVIDER environment variable.

Usage:
    from backend.services.ai import get_ai_service

    ai = get_ai_service()
    result = await ai.generate(system_prompt, user_prompt, temperature=0.3)

Supported providers:
    - ollama  (default, local development)
    - openai  (production)
"""

from backend.services.ai.ai_service import (
    BaseAIClient,
    ProviderRegistry,
    get_ai_service,
    reset_ai_service,
)

# Register built-in providers
from backend.services.ai.ollama_provider import OllamaProvider  # noqa: F401
from backend.services.ai.openai_provider import OpenAIProvider  # noqa: F401

ProviderRegistry.register("ollama", OllamaProvider)
ProviderRegistry.register("openai", OpenAIProvider)

__all__ = [
    "BaseAIClient",
    "ProviderRegistry",
    "get_ai_service",
    "reset_ai_service",
]
