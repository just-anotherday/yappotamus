"""Adapter from the existing provider registry to the intelligence AIProvider boundary."""

import time

from backend.intelligence.contracts import GenerationRequest, ProviderResult
from backend.services.ai.ai_service import ProviderRegistry


class RegistryAIProvider:
    def __init__(self, provider_name: str) -> None:
        self._provider_name = provider_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    async def generate(self, request: GenerationRequest) -> ProviderResult:
        provider_class = ProviderRegistry.get(self._provider_name)
        if provider_class is None:
            raise ValueError(f"unknown provider: {self._provider_name}")
        started = time.perf_counter()
        content = await provider_class().generate(
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            model=request.model,
        )
        duration_ms = round((time.perf_counter() - started) * 1000)
        return ProviderResult(content, self._provider_name, request.model, duration_ms)