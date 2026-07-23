"""AI Provider Exceptions

Domain-specific exceptions for AI provider operations.

Exception hierarchy:
    AIProviderError          — base exception for all AI provider errors
    └── AIValidationError    — invalid provider, model, or configuration (HTTP 400)
    └── AIConnectionError    — provider unreachable, offline, or timeout (HTTP 503)

Usage:
    from backend.services.ai.exceptions import AIValidationError, AIConnectionError

    raise AIValidationError("Model 'gpt-4o' not available on provider 'ollama'")
    raise AIConnectionError("Ollama service unreachable at http://localhost:11434")
"""

from typing import Optional


class AIProviderError(Exception):
    """Base exception for all AI provider errors."""

    def __init__(self, message: str, details: Optional[dict] = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AIValidationError(AIProviderError):
    """Raised when provider, model, or configuration is invalid.

    Maps to HTTP 400 Bad Request.

    Causes:
        - Unknown provider ID
        - Model not available on selected provider
        - Missing required configuration for provider
        - Invalid model format
    """


class AIConnectionError(AIProviderError):
    """Raised when the provider service is unreachable or times out.

    Maps to HTTP 503 Service Unavailable.

    Causes:
        - Ollama service offline
        - OpenAI API unreachable
        - Connection timeout during generation
        - Network error reaching provider
    """
