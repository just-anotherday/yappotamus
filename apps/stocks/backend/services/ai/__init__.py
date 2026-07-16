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

from backend.services.ai.ai_service import AIService, get_ai_service

__all__ = ["AIService", "get_ai_service"]
