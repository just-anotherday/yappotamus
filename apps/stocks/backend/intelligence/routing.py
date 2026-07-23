"""Validated, deterministic and configuration-driven routing policy."""

from __future__ import annotations

from dataclasses import dataclass

from backend.intelligence.contracts import RouteTarget, RoutingDecision, RoutingRequest


@dataclass(frozen=True)
class RoutingProfile:
    name: str
    default: RouteTarget
    premium: RouteTarget
    fallback_chain: tuple[RouteTarget, ...] = ()
    premium_token_threshold: int = 8_000


class DeterministicRoutingPolicy:
    def __init__(
        self,
        profiles: dict[str, RoutingProfile],
        configuration_revision: str,
        allowed_overrides: dict[str, frozenset[str]],
    ) -> None:
        if not profiles or not configuration_revision:
            raise ValueError("routing profiles and configuration revision are required")
        self._profiles = profiles
        self._revision = configuration_revision
        self._allowed_overrides = allowed_overrides

    async def decide(self, request: RoutingRequest) -> RoutingDecision:
        try:
            profile = self._profiles[request.deployment_profile]
        except KeyError as exc:
            raise ValueError(f"unknown deployment profile: {request.deployment_profile}") from exc

        reasons: list[str] = []
        rule_id = "profile-default"
        target = profile.default
        if request.provider_override or request.model_override:
            provider = request.provider_override or target.provider
            model = request.model_override or target.model
            if model not in self._allowed_overrides.get(provider, frozenset()):
                raise ValueError("provider/model override is not allowlisted")
            target = RouteTarget(provider, model)
            rule_id = "authenticated-override"
            reasons.append("allowlisted authenticated override")
        elif (
            request.estimated_tokens >= profile.premium_token_threshold
            or request.has_earnings
            or request.has_sec_content
        ):
            target = profile.premium
            rule_id = "material-or-large-input"
            reasons.append("measurable materiality or token threshold reached")
        else:
            reasons.append("profile default target")

        return RoutingDecision(
            target=target,
            rule_id=rule_id,
            deployment_profile=profile.name,
            configuration_revision=self._revision,
            reasons=tuple(reasons),
            fallback_chain=profile.fallback_chain,
        )