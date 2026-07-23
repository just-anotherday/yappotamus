"""Ollama-only composition root for automatic maintenance generation."""

from backend.config.settings import settings
from backend.intelligence.contracts import IntelligenceStage, RouteTarget, RoutingRequest
from backend.intelligence.providers import RegistryAIProvider
from backend.intelligence.routing import DeterministicRoutingPolicy, RoutingProfile


def build_maintenance_provider(model: str | None = None) -> tuple[dict[str, RegistryAIProvider], DeterministicRoutingPolicy]:
    if settings.MAINTENANCE_AI_PROVIDER != "ollama":
        raise ValueError("automatic maintenance provider must be ollama")
    selected_model = model or settings.OLLAMA_MODEL
    if selected_model not in settings.MAINTENANCE_OLLAMA_ALLOWED_MODELS:
        raise ValueError("maintenance Ollama model is not allowlisted")
    target = RouteTarget("ollama", selected_model)
    policy = DeterministicRoutingPolicy(
        profiles={"maintenance": RoutingProfile("maintenance", target, target, ())},
        configuration_revision=settings.INTELLIGENCE_ROUTING_REVISION,
        allowed_overrides={"ollama": frozenset(settings.MAINTENANCE_OLLAMA_ALLOWED_MODELS)},
    )
    return {"ollama": RegistryAIProvider("ollama")}, policy


async def maintenance_routing_decision(model: str | None = None):
    _, policy = build_maintenance_provider(model)
    return await policy.decide(RoutingRequest(
        stage=IntelligenceStage.ARTICLE,
        estimated_tokens=1,
        deployment_profile="maintenance",
    ))