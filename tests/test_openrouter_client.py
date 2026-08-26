"""Tests for the OpenRouter client.

All network calls are mocked with ``httpx.MockTransport``. No real OpenRouter
request is ever made and no live API key is used — the tests pass a dummy key
so header construction works without contacting anything.
"""

import json

import httpx
import pytest
from pydantic import SecretStr

from src import constants
from src.config import AppConfig
from src.openrouter_client import (
    AuthenticationError,
    ChatResult,
    EmptyContentError,
    InsufficientCreditsError,
    InvalidRequestError,
    InvalidResponseError,
    MissingAPIKeyError,
    NetworkError,
    OpenRouterClient,
    ProviderError,
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

        # Advertise temperature support so this auth/stream test sends it.
        _call(_client(handler), supported_parameters=["temperature", "max_tokens"])
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

    def test_normal_generation_sends_no_reasoning_override(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        # A normal interview call — even for a reasoning-capable model — must not
        # add a reasoning override (reasoning defaults to None).
        _call(
            _client(handler),
            supported_parameters=["temperature", "max_tokens", "reasoning"],
        )
        assert "reasoning" not in captured["body"]


# --- Connection test ---------------------------------------------------------


def _empty_body(finish_reason: str = "length", **overrides) -> dict:
    """A valid 2xx response whose model produced no visible text."""
    body = {
        "id": "gen-empty",
        "model": MODEL,
        "choices": [{"message": {"content": ""}, "finish_reason": finish_reason}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 128, "total_tokens": 133},
    }
    body.update(overrides)
    return body


def _sequence_client(bodies) -> tuple[OpenRouterClient, dict]:
    """A client that returns each body in turn; records the call count."""
    state = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        body = bodies[state["n"]]
        state["n"] += 1
        return httpx.Response(200, json=body)

    return _client(handler), state


class TestConnectionTest:
    def test_connection_test_uses_realistic_budget_and_prompt(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        result = _client(handler).test_connection()
        assert isinstance(result, ChatResult)
        # Realistic for reasoning models, but still intentionally cheap.
        assert captured["body"]["max_tokens"] == constants.CONNECTION_TEST_MAX_TOKENS
        assert captured["body"]["max_tokens"] == 256
        assert captured["body"]["messages"][0]["role"] == "user"
        assert captured["body"]["messages"][0]["content"] == constants.CONNECTION_TEST_PROMPT

    def test_connection_test_sends_minimal_reasoning_when_supported(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        _client(handler).test_connection(
            supported_parameters=["temperature", "max_tokens", "reasoning"]
        )
        assert captured["body"]["reasoning"]["effort"] == "minimal"
        assert captured["body"]["reasoning"]["exclude"] is True

    def test_connection_test_omits_reasoning_when_unsupported(self) -> None:
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        _client(handler).test_connection(
            supported_parameters=["temperature", "max_tokens"]
        )
        assert "reasoning" not in captured["body"]

    def test_successful_ok_response(self) -> None:
        body = _success_body(
            choices=[{"message": {"content": "OK"}, "finish_reason": "stop"}]
        )
        result = _client(lambda req: httpx.Response(200, json=body)).test_connection()
        assert result.content == "OK"

    def test_first_empty_then_success_retries_once(self) -> None:
        client, state = _sequence_client([_empty_body(), _success_body()])
        result = client.test_connection()
        assert result.content == "Hello"
        assert state["n"] == 2  # exactly one retry

    def test_both_empty_returns_controlled_error(self) -> None:
        client, state = _sequence_client([_empty_body(), _empty_body()])
        with pytest.raises(EmptyContentError) as raised:
            client.test_connection()
        assert state["n"] == 2  # no more than one retry
        assert "no text" in raised.value.message.lower()
        assert "test-key-not-real" not in str(raised.value)

    def test_provider_error_is_not_retried_as_empty(self) -> None:
        provider_body = {
            "id": "gen",
            "model": MODEL,
            "choices": [
                {
                    "message": {"content": None},
                    "finish_reason": "error",
                    "error": {"message": "upstream provider timeout"},
                }
            ],
        }
        client, state = _sequence_client([provider_body, _success_body()])
        with pytest.raises(ProviderError):
            client.test_connection()
        assert state["n"] == 1  # provider error stops immediately, no retry

    def test_connection_test_propagates_auth_error(self) -> None:
        client, state = _sequence_client([])  # handler overridden below

        def handler(request: httpx.Request) -> httpx.Response:
            state["n"] += 1
            return httpx.Response(401, json={"error": "bad"})

        client = _client(handler)
        with pytest.raises(AuthenticationError):
            client.test_connection()
        assert state["n"] == 1  # 401 is not retried

    def test_connection_test_propagates_insufficient_credits(self) -> None:
        client = _client(lambda req: httpx.Response(402, json={"error": "no credit"}))
        with pytest.raises(InsufficientCreditsError):
            client.test_connection()

    def test_connection_test_propagates_rate_limit(self) -> None:
        client = _client(lambda req: httpx.Response(429, json={"error": "slow down"}))
        with pytest.raises(RateLimitError):
            client.test_connection()


class TestEmptyContentHandling:
    def test_empty_content_raises_empty_content_error(self) -> None:
        client = _client(lambda req: httpx.Response(200, json=_empty_body()))
        with pytest.raises(EmptyContentError):
            _call(client)

    def test_empty_content_is_invalid_response_subclass(self) -> None:
        # Back-compatible: broad InvalidResponseError handling still catches it.
        assert issubclass(EmptyContentError, InvalidResponseError)
        client = _client(lambda req: httpx.Response(200, json=_empty_body()))
        with pytest.raises(InvalidResponseError):
            _call(client)

    def test_provider_error_in_2xx_raises_provider_error(self) -> None:
        body = {
            "id": "gen",
            "model": MODEL,
            "choices": [{"message": {"content": None}, "finish_reason": "error"}],
            "error": {"message": "provider unavailable"},
        }
        client = _client(lambda req: httpx.Response(200, json=body))
        with pytest.raises(ProviderError):
            _call(client)

    def test_normal_generation_does_not_retry_on_empty(self) -> None:
        # A single create_chat_completion must not retry; it fails once.
        client, state = _sequence_client([_empty_body(), _success_body()])
        with pytest.raises(EmptyContentError):
            _call(client)
        assert state["n"] == 1  # exactly one call — no automatic retry


class TestNoKeyInLogs:
    def test_api_key_never_appears_in_logs(self, caplog) -> None:
        import logging

        transport = httpx.MockTransport(
            lambda req: httpx.Response(200, json=_success_body())
        )
        client = OpenRouterClient(
            _config(), debug=True, http_client=httpx.Client(transport=transport)
        )
        with caplog.at_level(logging.DEBUG, logger="interview_practice_studio.openrouter"):
            client.test_connection()
        combined = " ".join(record.getMessage() for record in caplog.records)
        assert "test-key-not-real" not in combined
        assert "Authorization" not in combined
        assert "Bearer" not in combined


# --- Product hardening: parameter gating, routing, transient retries ---------


def _client_h(handler, sleeper=None) -> OpenRouterClient:
    """A client over a MockTransport handler with a no-op sleeper by default."""
    transport = httpx.MockTransport(handler)
    return OpenRouterClient(
        _config(),
        http_client=httpx.Client(transport=transport),
        sleeper=sleeper if sleeper is not None else (lambda _s: None),
    )


class TestParameterGating:
    def test_temperature_omitted_when_unsupported(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        client = _client_h(handler)
        client.create_chat_completion(
            model=MODEL,
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=64,
            supported_parameters=["max_tokens"],
        )
        assert "temperature" not in seen["payload"]

    def test_temperature_sent_when_supported(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        client = _client_h(handler)
        client.create_chat_completion(
            model=MODEL,
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=64,
            supported_parameters=["temperature", "max_tokens"],
        )
        assert seen["payload"]["temperature"] == 0.7

    def test_temperature_omitted_for_reasoning_model_without_metadata(self) -> None:
        # No metadata: fall back to the static list — gpt-5-mini rejects temperature.
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        _client_h(handler).create_chat_completion(
            model="openai/gpt-5-mini",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=64,
        )
        assert "temperature" not in seen["payload"]

    def test_temperature_sent_for_supporting_model_without_metadata(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        _client_h(handler).create_chat_completion(
            model="openai/gpt-4o-mini",  # not in MODELS_WITHOUT_TEMPERATURE
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=64,
        )
        assert seen["payload"]["temperature"] == 0.7

    def test_require_parameters_adds_provider_routing(self) -> None:
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["payload"] = json.loads(request.content)
            return httpx.Response(200, json=_success_body())

        client = _client_h(handler)
        client.create_chat_completion(
            model=MODEL,
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
            max_tokens=64,
            response_format={"type": "json_schema", "json_schema": {"name": "X"}},
            supported_parameters=["structured_outputs", "response_format"],
            require_parameters=True,
        )
        assert seen["payload"]["provider"] == {"require_parameters": True}
        assert seen["payload"]["response_format"]["type"] == "json_schema"


class TestTransientRetries:
    def test_retry_after_is_honoured_then_succeeds(self) -> None:
        calls = {"n": 0}
        slept: list[float] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                return httpx.Response(
                    429,
                    headers={"retry-after": "0"},
                    json={"error": {"message": "slow down"}},
                )
            return httpx.Response(200, json=_success_body())

        client = _client_h(handler, sleeper=lambda s: slept.append(s))
        result = _call(client)
        assert calls["n"] == 2  # one retry
        assert slept == [0.0]  # honoured Retry-After
        assert result.total_tokens == 20  # usage from the successful call only

    def test_network_error_is_retried_once_then_succeeds(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            if calls["n"] == 1:
                raise httpx.ConnectError("boom")
            return httpx.Response(200, json=_success_body())

        client = _client_h(handler)
        result = _call(client)
        assert calls["n"] == 2
        assert result.content == "Hello"

    def test_max_one_retry_on_persistent_503(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(503, json={"error": {"message": "overloaded"}})

        client = _client_h(handler)
        with pytest.raises(ServerError):
            _call(client)
        assert calls["n"] == 1 + constants.MAX_TRANSIENT_RETRIES

    def test_persistent_timeout_retried_then_raises(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            raise httpx.ReadTimeout("t")

        client = _client_h(handler)
        with pytest.raises(RequestTimeoutError):
            _call(client)
        assert calls["n"] == 1 + constants.MAX_TRANSIENT_RETRIES

    def test_invalid_request_is_not_retried(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(400, json={"error": {"message": "bad"}})

        client = _client_h(handler)
        with pytest.raises(InvalidRequestError):
            _call(client)
        assert calls["n"] == 1  # non-transient: no retry

    def test_auth_error_is_not_retried(self) -> None:
        calls = {"n": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            return httpx.Response(401, json={"error": {"message": "nope"}})

        client = _client_h(handler)
        with pytest.raises(AuthenticationError):
            _call(client)
        assert calls["n"] == 1
