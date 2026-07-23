"""AI Service - Unified interface for all LLM providers

Architecture:
  1. BaseAIClient          — abstract interface every provider implements
  2. ProviderRegistry      — dynamic registry; providers self-register via __init__.py
  3. generate_with_provider() — entry point that accepts explicit provider + model

To add a new provider:
  1. Create backend/services/ai/<name>_provider.py
  2. Implement BaseAIClient interface
  3. Register it in backend/services/ai/__init__.py
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from backend.config.settings import settings
from backend.services.ai.exceptions import AIConnectionError, AIValidationError

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
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Generate a text response from the LLM."""
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is reachable and configured."""
        ...

    @abstractmethod
    async def list_models(self) -> List[Dict[str, Any]]:
        """Return list of available models for this provider.

        Each dict should contain at minimum:
          - name (str): model identifier
          - size (int, optional): model size in bytes
          - modified_at (str, optional): last modified timestamp
        """
        ...

    def default_timeout(self) -> float:
        """Return default timeout in seconds for this provider.

        Subclasses may override to provide provider-specific defaults.
        Base default is 60 seconds.
        """
        return 60.0


# ---------------------------------------------------------------------------
# Provider Registry — dynamic registration, no hardcoded if/elif chains
# ---------------------------------------------------------------------------

class ProviderRegistry:
    """Registry mapping provider IDs to their concrete classes."""

    _providers: Dict[str, Type[BaseAIClient]] = {}

    @classmethod
    def register(cls, provider_id: str, provider_class: Type[BaseAIClient]) -> None:
        cls._providers[provider_id] = provider_class
        logger.info("[AI][Registry] Registered provider: %s (%s)", provider_id, provider_class.__name__)

    @classmethod
    def get(cls, provider_id: str) -> Optional[Type[BaseAIClient]]:
        return cls._providers.get(provider_id)

    @classmethod
    def all_ids(cls) -> List[str]:
        return list(cls._providers.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear registry (useful for testing)."""
        cls._providers.clear()


# ---------------------------------------------------------------------------
# Helper: instantiate a provider by ID
# ---------------------------------------------------------------------------

def _instantiate_provider(provider_id: str) -> BaseAIClient:
    """Instantiate the provider class registered under *provider_id*."""
    klass = ProviderRegistry.get(provider_id)
    if klass is None:
        available = ", ".join(ProviderRegistry.all_ids()) or "(none)"
        raise AIValidationError(
            f"Unknown AI provider '{provider_id}'. "
            f"Available providers: {available}"
        )
    return klass()


# ---------------------------------------------------------------------------
# Legacy helpers — kept for backward compatibility with existing callers
# ---------------------------------------------------------------------------

def _get_provider() -> BaseAIClient:
    """Factory: instantiate the correct provider based on AI_PROVIDER env var."""
    provider_name = settings.AI_PROVIDER
    logger.info("[AI] Using provider from AI_PROVIDER env var: '%s'", provider_name)
    return _instantiate_provider(provider_name)


# Module-level singleton (lazy-initialized on first call) — legacy global default
_ai_service: Optional[BaseAIClient] = None


def get_ai_service() -> BaseAIClient:
    """Return the globally configured AI service instance (legacy)."""
    global _ai_service
    if _ai_service is None:
        _ai_service = _get_provider()
    return _ai_service


def reset_ai_service():
    """Reset singleton (useful for testing)."""
    global _ai_service
    _ai_service = None


def resolve_provider_model(
    provider_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> tuple[str, str]:
    """Resolve normalized provider and model defaults without provider I/O."""
    resolved_provider = (provider_id or settings.AI_PROVIDER).strip().lower()
    resolved_model = (model_name or settings.default_model_for_provider(resolved_provider)).strip()

    if not resolved_model:
        raise AIValidationError(
            f"No default model is configured for provider '{resolved_provider}'"
        )
    return resolved_provider, resolved_model


async def validate_provider_model(
    provider_id: Optional[str] = None,
    model_name: Optional[str] = None,
) -> tuple[str, str, BaseAIClient]:
    """Resolve provider, check availability, and validate its model once.

    All deterministic validation occurs before generation/retry loops.
    """
    resolved_provider, resolved_model = resolve_provider_model(provider_id, model_name)
    client = _instantiate_provider(resolved_provider)

    if not await client.is_available():
        raise AIConnectionError(
            f"Provider '{resolved_provider}' is not available. Check configuration and connectivity."
        )

    models = await client.list_models()
    model_names = [
        item.get("name") if isinstance(item, dict) else getattr(item, "name", "")
        for item in models
    ]
    if resolved_model not in model_names:
        if resolved_provider == "openai":
            raise AIValidationError(f"Model {resolved_model} is not allowed")
        raise AIValidationError(
            f"Model '{resolved_model}' is not available for provider '{resolved_provider}'"
        )

    return resolved_provider, resolved_model, client


# ---------------------------------------------------------------------------
# Primary entry point: generate_with_provider() with full validation
# ---------------------------------------------------------------------------

async def generate_with_provider(
    provider_id: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.3,
    max_tokens: Optional[int] = None,
) -> str:
    """Generate text with explicit provider + model validation.

    Validation order:
      1. Resolve provider
      2. Provider exists?
      3. Provider available?
      4. Requested model allowed?
      5. Generate
      6. Save report

    Args:
        provider_id: Provider identifier (e.g., 'openai', 'ollama')
        model_name: Model name to use for generation
        system_prompt: System prompt text
        user_prompt: User prompt text
        temperature: Generation temperature (default 0.3)
        max_tokens: Maximum tokens to generate

    Returns:
        Generated text response

    Raises:
        AIValidationError: If validation fails at any step
    """
    # Step 1-2: Resolve provider + check exists
    provider_id, model_name, client = await validate_provider_model(
        provider_id, model_name
    )

    # Step 5: Generate
    result = await client.generate(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model_name,
    )

    logger.info(
        "[AI] Generated response with %s/%s (length: %d chars)",
        provider_id, model_name, len(result)
    )
    return result
