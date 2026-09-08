"""Provider-level coverage for native Ollama structured output."""

import json
import logging

import httpx
import pytest

from backend.models.analysis import (
    CorrectionPatchSet,
    FinancialAnalysisLLMResponse,
    FinancialAnalysisV2LLMResponse,
    GroundingReviewWireResponse,
)
from backend.services import ollama_service
from backend.services.ai.exceptions import (
    AIConnectionError,
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
    reviewer_response = {"f": {"s0": [{"r": "F", "p": "$463 is identified as support", "c": "DS", "a": [4], "m": [], "g": "TR"}]}}
    response = _FakeOllamaResponse(
        {"response": json.dumps(reviewer_response), "done": True, "done_reason": "stop"}
    )
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, response, **kwargs),
    )
    schema = ollama_service.build_request_local_review_schema(
        ["current_price"], coverage_segment_aliases=["s0"]
    )

    result = await OllamaProvider().generate(
        system_prompt="grounding reviewer",
        user_prompt="compact evidence manifest",
        model="compatible-model",
        temperature=0,
        response_schema=schema,
    )

    parsed = GroundingReviewWireResponse(**json.loads(result))
    assert parsed.f["s0"][0].a == [4]
    assert captured[0]["payload"]["stream"] is False
    assert captured[0]["payload"]["think"] is False
    assert captured[0]["payload"]["options"]["temperature"] == 0
    assert captured[0]["payload"]["format"] == schema
    claim_schema = schema["$defs"]["GroundingReviewWireFinding"]
    assert set(claim_schema["properties"]) == {"r", "p", "c", "a", "m", "i", "g"}
    assert "allOf" not in claim_schema and "oneOf" not in claim_schema
    assert captured[0]["payload"]["format"]["properties"]["f"] == {
        "type": "object",
        "properties": {
            "s0": {
                "type": "array",
                "items": {"$ref": "#/$defs/GroundingReviewWireFinding"},
                "minItems": 1,
            }
        },
        "required": ["s0"],
        "additionalProperties": False,
    }


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
async def test_openai_forwards_generic_json_schema_response_format(
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
        max_attempts=1,
    )

    assert json.loads(response) == {"asset": "AMD"}
    assert len(captured) == 1
    assert captured[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert "format" not in captured[0]["payload"]
    assert captured[0]["payload"]["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "structured_response",
            "strict": False,
            "schema": FinancialAnalysisLLMResponse.model_json_schema(),
        },
    }


@pytest.mark.asyncio
async def test_openai_forwards_required_alias_reviewer_schema_without_weakening(monkeypatch):
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
    schema = ollama_service.build_request_local_review_schema(
        ["current_price"], coverage_segment_aliases=["s23", "s24", "s25"]
    )

    await OpenAIProvider().generate(
        system_prompt="reviewer",
        user_prompt="safe fixture",
        model="gpt-4o-mini",
        response_schema=schema,
        max_attempts=1,
    )

    supplied = captured[0]["payload"]["response_format"]["json_schema"]
    assert supplied["schema"] == schema
    assert supplied["strict"] is False  # Existing generic adapter behavior.
    keyed = supplied["schema"]["properties"]["f"]
    assert keyed["required"] == ["s23", "s24", "s25"]
    assert keyed["additionalProperties"] is False
    assert all(item["minItems"] == 1 for item in keyed["properties"].values())


@pytest.mark.asyncio
async def test_openai_and_ollama_receive_the_same_complete_v2_schema(monkeypatch):
    ollama_captured = []
    openai_captured = []

    class _CapturingOpenAIClient(_CapturingAsyncClient):
        async def post(self, url, json, headers):
            openai_captured.append({"url": url, "payload": json, "headers": headers})
            return _FakeOpenAIResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(ollama_captured, **kwargs),
    )
    schema = FinancialAnalysisV2LLMResponse.model_json_schema()

    await OllamaProvider().generate(
        system_prompt="v2 system",
        user_prompt="v2 user",
        model="compatible-model",
        response_schema=schema,
    )
    monkeypatch.setattr(
        "backend.services.ai.openai_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingOpenAIClient([], **kwargs),
    )
    await OpenAIProvider().generate(
        system_prompt="v2 system",
        user_prompt="v2 user",
        model="gpt-4o-mini",
        response_schema=schema,
        max_attempts=1,
    )

    ollama_schema = ollama_captured[0]["payload"]["format"]
    openai_schema = openai_captured[0]["payload"]["response_format"][
        "json_schema"
    ]["schema"]
    assert ollama_schema == openai_schema == schema
    assert set(schema["required"]) == set(schema["properties"])


@pytest.mark.asyncio
async def test_openai_non_schema_request_shape_remains_backward_compatible(monkeypatch):
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

    await OpenAIProvider().generate(
        system_prompt="system",
        user_prompt="user",
        model="gpt-4o-mini",
    )

    assert len(captured) == 1
    assert "response_format" not in captured[0]["payload"]
    assert captured[0]["payload"]["temperature"] == 0.3


@pytest.mark.asyncio
async def test_openai_rejects_non_object_schema_before_network(monkeypatch):
    post_called = False

    class _UnexpectedOpenAIClient(_CapturingAsyncClient):
        async def post(self, url, json, headers):
            nonlocal post_called
            post_called = True
            return _FakeOpenAIResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    monkeypatch.setattr(
        "backend.services.ai.openai_provider.httpx.AsyncClient",
        lambda **kwargs: _UnexpectedOpenAIClient([], **kwargs),
    )

    with pytest.raises(AIValidationError, match="JSON Schema object"):
        await OpenAIProvider().generate(
            system_prompt="system",
            user_prompt="user",
            model="gpt-4o-mini",
            response_schema="json",
        )

    assert post_called is False


@pytest.mark.asyncio
async def test_openai_explicit_single_attempt_stops_after_transport_failure(monkeypatch):
    post_count = 0

    class _FailingOpenAIClient(_CapturingAsyncClient):
        async def post(self, url, json, headers):
            nonlocal post_count
            post_count += 1
            raise httpx.ConnectError("transient transport failure")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    monkeypatch.setattr(
        "backend.services.ai.openai_provider.httpx.AsyncClient",
        lambda **kwargs: _FailingOpenAIClient([], **kwargs),
    )

    with pytest.raises(AIConnectionError, match="after 1 attempt"):
        await OpenAIProvider().generate(
            system_prompt="system",
            user_prompt="patch correction",
            model="gpt-4o-mini",
            max_attempts=1,
        )

    assert post_count == 1


@pytest.mark.asyncio
async def test_openai_explicit_single_attempt_stops_after_http_failure(monkeypatch):
    post_count = 0

    class _FailedOpenAIResponse:
        status_code = 503
        text = "present"
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")

        def json(self):
            return {"error": "unavailable"}

    class _FailingOpenAIClient(_CapturingAsyncClient):
        async def post(self, url, json, headers):
            nonlocal post_count
            post_count += 1
            return _FailedOpenAIResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    monkeypatch.setattr(
        "backend.services.ai.openai_provider.httpx.AsyncClient",
        lambda **kwargs: _FailingOpenAIClient([], **kwargs),
    )

    with pytest.raises(AIConnectionError, match="after 1 attempt"):
        await OpenAIProvider().generate(
            system_prompt="system",
            user_prompt="patch correction",
            model="gpt-4o-mini",
            max_attempts=1,
        )

    assert post_count == 1


@pytest.mark.asyncio
async def test_openai_default_retry_behavior_remains_three_attempts(monkeypatch):
    post_count = 0

    class _RetryingOpenAIClient(_CapturingAsyncClient):
        async def post(self, url, json, headers):
            nonlocal post_count
            post_count += 1
            if post_count == 1:
                raise httpx.ConnectError("transient transport failure")
            return _FakeOpenAIResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    monkeypatch.setattr(
        "backend.services.ai.openai_provider.httpx.AsyncClient",
        lambda **kwargs: _RetryingOpenAIClient([], **kwargs),
    )

    response = await OpenAIProvider().generate(
        system_prompt="system",
        user_prompt="primary generation",
        model="gpt-4o-mini",
    )

    assert json.loads(response) == {"asset": "AMD"}
    assert post_count == 2


@pytest.mark.asyncio
async def test_openai_explicit_two_attempt_limit_is_honored(monkeypatch):
    post_count = 0

    class _FailingOpenAIClient(_CapturingAsyncClient):
        async def post(self, url, json, headers):
            nonlocal post_count
            post_count += 1
            raise httpx.ConnectError("transport failure")

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")
    monkeypatch.setattr(
        "backend.services.ai.openai_provider.httpx.AsyncClient",
        lambda **kwargs: _FailingOpenAIClient([], **kwargs),
    )

    with pytest.raises(AIConnectionError, match="after 2 attempt"):
        await OpenAIProvider().generate(
            system_prompt="system",
            user_prompt="user",
            model="gpt-4o-mini",
            max_attempts=2,
        )

    assert post_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("max_attempts", [True, 0, -1, 4, 1.5, "1"])
async def test_openai_rejects_invalid_explicit_attempt_limits(monkeypatch, max_attempts):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_ALLOWED_MODELS", "gpt-4o-mini")

    with pytest.raises(AIValidationError, match="max_attempts"):
        await OpenAIProvider().generate(
            system_prompt="system",
            user_prompt="user",
            model="gpt-4o-mini",
            max_attempts=max_attempts,
        )


@pytest.mark.asyncio
async def test_request_local_patch_schema_is_forwarded_to_ollama(monkeypatch):
    captured = []
    response = _FakeOllamaResponse({
        "response": json.dumps({
            "patches": [{
                "target_id": "bull_case[0].segment_0",
                "operation": "DELETE",
                "replacement": None,
                "article_indices_used": [],
            }]
        }),
        "done": True,
    })
    monkeypatch.setattr(
        "backend.services.ai.ollama_provider.httpx.AsyncClient",
        lambda **kwargs: _CapturingAsyncClient(captured, response, **kwargs),
    )
    schema = ollama_service.build_request_local_patch_schema([
        "bull_case[0].segment_0"
    ])

    result = await OllamaProvider().generate(
        system_prompt="patch correction",
        user_prompt="one target",
        model="compatible-model",
        response_schema=schema,
    )

    assert CorrectionPatchSet(**json.loads(result)).patches[0].operation == "DELETE"
    assert captured[0]["payload"]["format"] == schema
    assert captured[0]["payload"]["stream"] is False
    assert captured[0]["payload"]["think"] is False
    assert captured[0]["payload"]["options"]["temperature"] == 0
