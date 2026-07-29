"""Tests for the OpenRouter client.

All network calls are mocked with ``httpx.MockTransport``. No real OpenRouter
request is ever made and no live API key is used — the tests pass a dummy key
so header construction works without contacting anything.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from src.config import AppConfig
from src.openrouter_client import (
    AuthenticationError,
    ChatResult,
    InsufficientCreditsError,
    InvalidRequestError,
    InvalidResponseError,
    MissingAPIKeyError,
    NetworkError,
    OpenRouterClient,
    RateLimitError,
    RequestTimeoutError,
    ServerError,
    UnsupportedParameterError,
)

MODEL = "openai/gpt-5-mini"


def _config() -> AppConfig:
    return AppConfig(api_key=SecretStr("test-key-not-real"))


def _client(handler) -> OpenRouterClient:
    transport = httpx.MockTransport(handler)
    return OpenRouterClient(_config(), http_client=httpx.Client(transport=transport))


def _success_body(**overrides) -> dict:
    body = {
        "id": "gen-abc123",
        "model": MODEL,
        "choices": [{"message": {"content": "Hello"}, "finish_reason": "stop"}],
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
            "cost": 0.00123,
        },
    }
    body.update(overrides)
    return body


def _call(client: OpenRouterClient, **kwargs) -> ChatResult:
    params = dict(
        model=MODEL,
        messages=[{"role": "user", "content": "hi"}],
        temperature=0.2,
        max_tokens=64,
    )
    params.update(kwargs)
    return client.create_chat_completion(**params)


# --- Success path ------------------------------------------------------------


class TestSuccess:
    def test_successful_completion_extracts_all_fields(self) -> None:
        client = _client(lambda req: httpx.Response(200, json=_success_body()))
        result = _call(client)
        assert result.content == "Hello"
        assert result.model == MODEL
        assert result.prompt_tokens == 12
        assert result.completion_tokens == 8
        assert result.total_tokens == 20
        assert result.reported_cost == 0.00123
        assert result.request_id == "gen-abc123"
        assert result.finish_reason == "stop"
        assert result.usage_available is True
        assert result.duration_seconds >= 0

    def test_request_uses_bearer_auth_and_is_non_streaming(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization")
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        _call(_client(handler))
        assert captured["auth"] == "Bearer test-key-not-real"
        assert captured["body"]["stream"] is False
        assert captured["body"]["model"] == MODEL
        assert captured["body"]["temperature"] == 0.2
        assert captured["body"]["max_tokens"] == 64

    def test_debug_info_is_safe(self) -> None:
        client = _client(lambda req: httpx.Response(200, json=_success_body()))
        info = _call(client).debug_info
        # Only non-sensitive metadata is exposed.
        assert set(vars(info)) == {
            "request_id",
            "model",
            "duration_seconds",
            "status_category",
        }
        assert info.status_category == "success"


# --- HTTP error mapping ------------------------------------------------------


class TestHttpErrors:
    @pytest.mark.parametrize(
        "status,exc",
        [
            (400, InvalidRequestError),
            (401, AuthenticationError),
            (402, InsufficientCreditsError),
            (429, RateLimitError),
            (500, ServerError),
            (503, ServerError),
        ],
    )
    def test_status_maps_to_exception(self, status: int, exc: type) -> None:
        client = _client(
            lambda req: httpx.Response(status, json={"error": {"message": "nope"}})
        )
        with pytest.raises(exc) as raised:
            _call(client)
        assert raised.value.status_code == status

    def test_error_message_is_safe_and_short(self) -> None:
        client = _client(
            lambda req: httpx.Response(401, json={"error": {"message": "x" * 999}})
        )
        with pytest.raises(AuthenticationError) as raised:
            _call(client)
        # No credentials leak; message is a controlled string.
        assert "test-key-not-real" not in str(raised.value)


# --- Transport failures ------------------------------------------------------


class TestTransportFailures:
    def test_timeout_maps_to_request_timeout(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        with pytest.raises(RequestTimeoutError):
            _call(_client(handler))

    def test_network_error_maps_to_network_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(NetworkError):
            _call(_client(handler))


# --- Malformed responses -----------------------------------------------------


class TestMalformedResponses:
    def test_invalid_json_raises(self) -> None:
        client = _client(lambda req: httpx.Response(200, text="not json at all"))
        with pytest.raises(InvalidResponseError):
            _call(client)

    def test_empty_choices_raises(self) -> None:
        body = _success_body(choices=[])
        client = _client(lambda req: httpx.Response(200, json=body))
        with pytest.raises(InvalidResponseError):
            _call(client)

    def test_missing_usage_degrades_gracefully(self) -> None:
        body = _success_body()
        del body["usage"]
        client = _client(lambda req: httpx.Response(200, json=body))
        result = _call(client)
        # Content is still usable; usage is marked unavailable.
        assert result.content == "Hello"
        assert result.usage_available is False
        assert result.prompt_tokens == 0
        assert result.total_tokens == 0
        assert result.reported_cost is None

    def test_usage_without_cost_has_no_reported_cost(self) -> None:
        body = _success_body(
            usage={"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}
        )
        client = _client(lambda req: httpx.Response(200, json=body))
        result = _call(client)
        assert result.usage_available is True
        assert result.reported_cost is None
        assert result.total_tokens == 10


# --- Missing key & unsupported parameters ------------------------------------


class TestKeyAndParameters:
    def test_missing_api_key_raises_before_network(self) -> None:
        # Unconfigured config; handler would fail the test if ever called.
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("no network call should happen without a key")

        client = OpenRouterClient(
            AppConfig(), http_client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        with pytest.raises(MissingAPIKeyError):
            _call(client)

    def test_unsupported_response_format_raises_before_network(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("unsupported parameter must fail before network")

        client = _client(handler)
        with pytest.raises(UnsupportedParameterError):
            _call(
                client,
                response_format={"type": "json_object"},
                supported_parameters=["temperature", "max_tokens"],
            )

    def test_supported_response_format_is_sent(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        _call(
            _client(handler),
            response_format={"type": "json_object"},
            supported_parameters=["temperature", "max_tokens", "response_format"],
        )
        assert captured["body"]["response_format"] == {"type": "json_object"}

    def test_response_format_omitted_when_not_requested(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        _call(_client(handler))
        assert "response_format" not in captured["body"]


# --- Connection test ---------------------------------------------------------


class TestConnectionTest:
    def test_connection_test_makes_a_tiny_request(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        result = _client(handler).test_connection()
        assert isinstance(result, ChatResult)
        assert captured["body"]["max_tokens"] <= 8
        assert captured["body"]["messages"][0]["role"] == "user"

    def test_connection_test_propagates_auth_error(self) -> None:
        client = _client(lambda req: httpx.Response(401, json={"error": "bad"}))
        with pytest.raises(AuthenticationError):
            client.test_connection()
