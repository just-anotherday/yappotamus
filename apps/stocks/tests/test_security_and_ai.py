"""Focused single-user authentication and AI cost-control tests."""

from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import Depends, FastAPI

from backend.auth import verify_app_access_token
from backend.config.settings import Settings
from backend.exceptions import register_exception_handlers
from backend.models.analysis import FinancialAnalysisRequest, NewsArticleRequest, PriceDataRequest
from backend.routers.auth import router as auth_router
from backend.routers.analysis import router as analysis_router
from backend.services.ai import ProviderRegistry
from backend.services.ai.ai_service import BaseAIClient, validate_provider_model
from backend.services.ai.exceptions import AIConnectionError, AIValidationError
from backend.services.ai.openai_provider import OpenAIProvider
from backend.services.ollama_service import generate_analysis


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def auth_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(auth_router, dependencies=[Depends(verify_app_access_token)])
    return app


@pytest.mark.asyncio
async def test_auth_missing_wrong_and_correct_token(auth_app, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_TOKEN", "correct-token")
    transport = httpx.ASGITransport(app=auth_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        assert (await client.get("/api/auth/verify")).status_code == 401
        assert (
            await client.get(
                "/api/auth/verify", headers={"Authorization": "Bearer wrong-token"}
            )
        ).status_code == 401
        response = await client.get(
            "/api/auth/verify", headers={"Authorization": "Bearer correct-token"}
        )

    assert response.status_code == 200
    assert response.json() == {"authenticated": True}


def test_missing_app_access_token_fails_clearly(monkeypatch):
    monkeypatch.delenv("APP_ACCESS_TOKEN", raising=False)
    with pytest.raises(EnvironmentError, match="^APP_ACCESS_TOKEN is required$"):
        Settings().validate()


def test_openai_allowlist_parsing_and_defaults(monkeypatch):
    monkeypatch.setenv(
        "OPENAI_ALLOWED_MODELS",
        " gpt-4o-mini, gpt-4.1-mini,gpt-4o-mini, ",
    )
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    settings = Settings()
    assert settings.OPENAI_MODEL == "gpt-4o-mini"
    assert settings.OPENAI_ALLOWED_MODELS == ["gpt-4o-mini", "gpt-4.1-mini"]


@pytest.mark.asyncio
async def test_openai_lists_only_allowlisted_models(monkeypatch):
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini,gpt-4.1-mini")
    models = await OpenAIProvider().list_models()
    assert [model["name"] for model in models] == ["gpt-4o-mini", "gpt-4.1-mini"]


@pytest.mark.asyncio
async def test_openai_invalid_model_makes_zero_http_requests(monkeypatch):
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    post = AsyncMock()
    monkeypatch.setattr(httpx.AsyncClient, "post", post)

    with pytest.raises(AIValidationError, match="Model gpt-4o is not allowed"):
        await OpenAIProvider().generate("system", "user", model="gpt-4o")

    post.assert_not_awaited()


class UnavailableProvider(BaseAIClient):
    async def generate(self, *args, **kwargs):
        raise AssertionError("generation must not run")

    async def is_available(self):
        return False

    async def list_models(self):
        return [{"name": "test-model"}]


@pytest.mark.asyncio
async def test_unknown_and_unavailable_provider_errors():
    with pytest.raises(AIValidationError, match="Unknown AI provider"):
        await validate_provider_model("does-not-exist", "model")

    ProviderRegistry.register("unavailable-test", UnavailableProvider)
    try:
        with pytest.raises(AIConnectionError, match="is not available"):
            await validate_provider_model("unavailable-test", "test-model")
    finally:
        ProviderRegistry._providers.pop("unavailable-test", None)


def _analysis_request() -> FinancialAnalysisRequest:
    return FinancialAnalysisRequest(
        ticker="TEST",
        news_articles=[NewsArticleRequest(title="Test article")],
        price_data=PriceDataRequest(
            current_price=1,
            daily_change_percent=0,
            fifty_two_week_high=1,
            fifty_two_week_low=1,
            trading_volume=1,
        ),
    )


@pytest.mark.asyncio
async def test_invalid_openai_model_has_zero_generation_retries(monkeypatch):
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    generate = AsyncMock()
    monkeypatch.setattr(OpenAIProvider, "generate", generate)

    with pytest.raises(AIValidationError, match="Model gpt-4o is not allowed"):
        await generate_analysis(
            _analysis_request(), provider="openai", model="gpt-4o"
        )

    generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_ai_errors_map_to_http_statuses(monkeypatch):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(analysis_router)

    async def validation_failure(*args, **kwargs):
        raise AIValidationError("bad model")

    monkeypatch.setattr("backend.routers.analysis.generate_analysis", validation_failure)
    transport = httpx.ASGITransport(app=app)
    payload = _analysis_request().model_dump(mode="json")
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/analysis/generate", json=payload)
    assert response.status_code == 400

    async def connection_failure(*args, **kwargs):
        raise AIConnectionError("provider unavailable")

    monkeypatch.setattr("backend.routers.analysis.generate_analysis", connection_failure)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/analysis/generate", json=payload)
    assert response.status_code == 503