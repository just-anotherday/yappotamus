"""Provider-level coverage for native Ollama structured output."""

import json
import logging

import pytest

from backend.models.analysis import FinancialAnalysisLLMResponse, GroundingReviewWireResponse
from backend.services import ollama_service
from backend.services.ai.exceptions import (
    AIHTTPError,
    AIResponseEnvelopeError,
    AIValidationError,
)
from backend.services.ai.ollama_provider import OllamaProvider
from backend.services.ai.openai_provider import OpenAIProvider


class _FakeOllamaResponse:
    def __init__(self, envelope=None, *, status_code=200):
        self.envelope = (
            {"response": json.dumps({"asset": "AMD"}), "done": True}
            if envelope is None
            else envelope
        )
        self.status_code = status_code
        self.headers = {"content-type": "application/json; charset=utf-8"}

    def json(self):
        return self.envelope


class _CapturingAsyncClient:
    def __init__(self, captured, response=None, **kwargs):
        self.captured = captured
        self.timeout = kwargs.get("timeout")
        self.response = response or _FakeOllamaResponse()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, url, json):
        self.captured.append({"url": url, "payload": json, "timeout": self.timeout})
        return self.response


@pytest.mark.asyncio
async def test_ollama_generate_sends_the_strict_pydantic_schema(monkeypatch):
    captured = []
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, **kwargs),
    )
    provider = OllamaProvider()
    schema = FinancialAnalysisLLMResponse.model_json_schema()

    response = await provider.generate(
        system_prompt="system",
        user_prompt="user",
        model="compatible-model",
        max_tokens=8064,
        response_schema=schema,
    )

    assert json.loads(response) == {"asset": "AMD"}
    assert len(captured) == 1
    assert captured[0]["url"].endswith("/api/generate")
    assert captured[0]["payload"]["format"] == schema
    assert captured[0]["payload"]["stream"] is False
    assert captured[0]["payload"]["think"] is False
    assert captured[0]["payload"]["model"] == "compatible-model"
    assert captured[0]["payload"]["options"]["temperature"] == 0
    assert captured[0]["payload"]["options"]["num_predict"] == 8064


@pytest.mark.asyncio
async def test_grounding_reviewer_uses_native_ollama_structured_output(monkeypatch):
    captured = []
    reviewer_response = {"f": [{"s": "s0", "r": "F", "p": "$463 is identified as support", "c": "DS", "a": [4], "m": [], "g": "TR"}]}
    response = _FakeOllamaResponse(
        {"response": json.dumps(reviewer_response), "done": True, "done_reason": "stop"}
    )
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, response, **kwargs),
    )
    schema = ollama_service.build_request_local_review_schema(["current_price"])

    result = await OllamaProvider().generate(
        system_prompt="grounding reviewer",
        user_prompt="compact evidence manifest",
        model="compatible-model",
        temperature=0,
        response_schema=schema,
    )

    parsed = GroundingReviewWireResponse(**json.loads(result))
    assert parsed.f[0].a == [4]
    assert captured[0]["payload"]["stream"] is False
    assert captured[0]["payload"]["think"] is False
    assert captured[0]["payload"]["options"]["temperature"] == 0
    assert captured[0]["payload"]["format"] == schema
    claim_schema = schema["$defs"]["GroundingReviewWireFinding"]
    assert set(claim_schema["properties"]) == {"s", "r", "p", "c", "a", "m", "i", "g"}
    assert "allOf" not in claim_schema and "oneOf" not in claim_schema


@pytest.mark.asyncio
async def test_ollama_extracts_only_top_level_generate_response(monkeypatch):
    captured = []
    generated = '{"asset":"AMD"}'
    response = _FakeOllamaResponse(
        {
            "response": generated,
            "message": {"content": '{"asset":"WRONG"}'},
            "done": True,
        }
    )
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, response, **kwargs),
    )

    result = await OllamaProvider().generate(
        system_prompt="system",
        user_prompt="user",
        response_schema={"type": "object"},
    )

    assert result == generated
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_chat_style_envelope_is_rejected_without_provider_retry(monkeypatch):
    captured = []
    response = _FakeOllamaResponse(
        {"message": {"content": '{"asset":"AMD"}'}, "done": True}
    )
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, response, **kwargs),
    )

    with pytest.raises(
        AIResponseEnvelopeError,
        match="did not contain a string response field",
    ) as exc_info:
        await OllamaProvider().generate(
            system_prompt="system",
            user_prompt="user",
            response_schema={"type": "object"},
        )

    assert exc_info.value.details["failure_kind"] == "invalid_response_envelope"
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_empty_response_with_thinking_is_safe_and_specific(
    monkeypatch,
    caplog,
):
    captured = []
    response = _FakeOllamaResponse(
        {
            "response": "",
            "thinking": "private reasoning must not be logged or consumed",
            "done": True,
            "done_reason": "stop",
        }
    )
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, response, **kwargs),
    )

    with caplog.at_level(logging.INFO, logger="backend.services.ai.ollama_provider"):
        with pytest.raises(
            AIResponseEnvelopeError,
            match="empty generated response",
        ) as exc_info:
            await OllamaProvider().generate(
                system_prompt="system",
                user_prompt="user",
                response_schema={"type": "object"},
            )

    assert exc_info.value.details == {
        "failure_kind": "empty_generated_response",
        "thinking_present": True,
    }
    assert len(captured) == 1
    assert "response_len=0" in caplog.text
    assert "thinking_present=True" in caplog.text
    assert "thinking_len=48" in caplog.text
    assert "private reasoning" not in caplog.text


@pytest.mark.asyncio
async def test_non_success_http_response_is_not_a_connection_error(monkeypatch):
    captured = []
    response = _FakeOllamaResponse({}, status_code=500)
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, response, **kwargs),
    )

    with pytest.raises(AIHTTPError) as exc_info:
        await OllamaProvider().generate(system_prompt="system", user_prompt="user")

    assert exc_info.value.details == {"provider": "ollama", "status_code": 500}
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_ollama_rejects_a_non_object_response_schema_before_network(
    monkeypatch,
):
    post_called = False

    class _UnexpectedClient(_CapturingAsyncClient):
        async def post(self, url, json):
            nonlocal post_called
            post_called = True
            return await super().post(url, json)

    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _UnexpectedClient([], **kwargs),
    )

    with pytest.raises(AIValidationError, match="JSON Schema object"):
        await OllamaProvider().generate(
            system_prompt="system",
            user_prompt="user",
            response_schema="json",
        )

    assert post_called is False


class _FakeOpenAIResponse:
    status_code = 200
    text = "present"

    def json(self):
        return {
            "choices": [
                {"message": {"content": '{"asset": "AMD"}'}}
            ]
        }


@pytest.mark.asyncio
async def test_shared_schema_does_not_change_the_openai_request_payload(
    monkeypatch,
):
    captured = []

    class _CapturingOpenAIClient(_CapturingAsyncClient):
        async def post(self, url, json, headers):
            captured.append({"url": url, "payload": json, "headers": headers})
            return _FakeOpenAIResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    monkeypatch.setattr(
        "backend.services.ai.openai_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingOpenAIClient([], **kwargs),
    )

    response = await OpenAIProvider().generate(
        system_prompt="system",
        user_prompt="user",
        model="gpt-4o-mini",
        response_schema=FinancialAnalysisLLMResponse.model_json_schema(),
    )

    assert json.loads(response) == {"asset": "AMD"}
    assert len(captured) == 1
    assert captured[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert "format" not in captured[0]["payload"]
    assert "response_format" not in captured[0]["payload"]
