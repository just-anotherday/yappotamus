"""Single narrow composition root for intelligence orchestration boundaries."""

from backend.config.settings import settings
from backend.intelligence.contracts import RouteTarget
from backend.intelligence.providers import RegistryAIProvider
from backend.intelligence.routing import DeterministicRoutingPolicy, RoutingProfile


def build_routing_policy(*, automatic: bool = False) -> DeterministicRoutingPolicy:
    ollama = RouteTarget("ollama", settings.OLLAMA_MODEL)
    openai = RouteTarget("openai", settings.OPENAI_MODEL)
    if automatic and not settings.OPENAI_AUTOMATIC_GENERATION_ENABLED and settings.INTELLIGENCE_ROUTING_PROFILE != "local-only":
        raise ValueError("automatic OpenAI generation is disabled; INTELLIGENCE_ROUTING_PROFILE must be local-only")
    if not automatic and not settings.OPENAI_MANUAL_GENERATION_ENABLED and settings.INTELLIGENCE_ROUTING_PROFILE != "local-only":
        raise ValueError("manual OpenAI generation is disabled; INTELLIGENCE_ROUTING_PROFILE must be local-only")
    profiles = {
        "local-only": RoutingProfile("local-only", ollama, ollama),
        "hybrid": RoutingProfile("hybrid", ollama, openai, (ollama,)),
        "premium-only": RoutingProfile("premium-only", openai, openai),
    }
    return DeterministicRoutingPolicy(
        profiles, settings.INTELLIGENCE_ROUTING_REVISION,
        {"ollama": frozenset({settings.OLLAMA_MODEL}), "openai": frozenset(settings.OPENAI_ALLOWED_MODELS)},
    )


def build_providers() -> dict[str, RegistryAIProvider]:
    return {name: RegistryAIProvider(name) for name in ("ollama", "openai")}