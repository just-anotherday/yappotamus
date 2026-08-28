"""AI Provider Exceptions

Domain-specific exceptions for AI provider operations.

Exception hierarchy:
    AIProviderError          — base exception for all AI provider errors
    └── AIValidationError    — invalid provider, model, or configuration (HTTP 400)
    └── AIConnectionError    — provider unreachable, offline, or timeout (HTTP 503)
    └── AIHTTPError          — provider returned a non-success HTTP response (HTTP 502)
    └── AIStructuredOutputError — malformed or schema-invalid model output (HTTP 502)
        └── AIResponseEnvelopeError — invalid/empty provider response envelope (HTTP 502)

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


class AIHTTPError(AIProviderError):
    """Raised when a reachable provider returns a non-success HTTP response.

    Maps to HTTP 502 Bad Gateway. Details must contain only safe response metadata,
    never the provider response body.
    """


class AIStructuredOutputError(AIProviderError):
    """Raised when generation succeeds but no valid structured report is produced.

    Maps to HTTP 502 Bad Gateway because the selected upstream model responded,
    but its response could not satisfy the application's report contract.
    """


class AISemanticGroundingError(AIStructuredOutputError):
    """Raised when a structured report cannot satisfy grounding rules.

    Maps to HTTP 502 without exposing the rejected model output. This remains
    distinct from malformed JSON, schema validation, and citation attribution.
    """


class AIResponseEnvelopeError(AIStructuredOutputError):
    """Raised when an HTTP-success provider envelope has no usable output text."""
