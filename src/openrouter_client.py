"""OpenRouter Chat Completions client.

A small, typed, non-streaming client for the OpenRouter chat-completions
endpoint. It reads the API key securely from :class:`~src.config.AppConfig`,
authenticates with a Bearer token, uses explicit connection and read timeouts,
and maps every failure mode to a specific, catchable exception.

Privacy: by default the client logs **nothing** about a request. It never logs
headers, credentials or message content. A safe debug mode logs only
non-sensitive metadata (request ID, model, duration and a coarse status
category) via :class:`RequestDebugInfo`.
"""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import httpx

from src import constants
from src.config import AppConfig

__all__ = [
    "OpenRouterError",
    "MissingAPIKeyError",
    "InvalidRequestError",
    "AuthenticationError",
    "InsufficientCreditsError",
    "RateLimitError",
    "ServerError",
    "RequestTimeoutError",
    "NetworkError",
    "InvalidResponseError",
    "EmptyContentError",
    "ProviderError",
    "UnsupportedParameterError",
    "ChatResult",
    "RequestDebugInfo",
    "OpenRouterClient",
]

logger = logging.getLogger("interview_practice_studio.openrouter")


# --- Exceptions --------------------------------------------------------------


class OpenRouterError(Exception):
    """Base class for all OpenRouter client errors.

    ``message`` is safe to show to a user. ``status_code`` and ``category`` are
    present when the error came from an HTTP response.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        category: str = "error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.category = category


class MissingAPIKeyError(OpenRouterError):
    """No API key was configured."""


class InvalidRequestError(OpenRouterError):
    """The request was rejected as invalid (HTTP 400)."""


class AuthenticationError(OpenRouterError):
    """Authentication failed (HTTP 401)."""


class InsufficientCreditsError(OpenRouterError):
    """The account has insufficient credits (HTTP 402)."""


class RateLimitError(OpenRouterError):
    """The request was rate limited (HTTP 429)."""


class ServerError(OpenRouterError):
    """OpenRouter or the upstream model returned a server error (HTTP >= 500)."""


class RequestTimeoutError(OpenRouterError):
    """The request timed out."""


class NetworkError(OpenRouterError):
    """A network-level failure prevented the request from completing."""


class InvalidResponseError(OpenRouterError):
    """The response was not valid or was missing required content."""


class EmptyContentError(InvalidResponseError):
    """A valid HTTP response whose model generated no visible assistant text.

    A subclass of :class:`InvalidResponseError` so existing broad handling still
    catches it, while callers (the connection test) can distinguish a genuine
    no-content generation — which may be worth one retry — from a malformed
    response or a provider error.
    """


class ProviderError(OpenRouterError):
    """The upstream provider reported an error inside an otherwise-2xx response."""


class UnsupportedParameterError(OpenRouterError):
    """A requested parameter is not supported by the selected model."""


# --- Typed results -----------------------------------------------------------


@dataclass(frozen=True)
class RequestDebugInfo:
    """Non-sensitive request metadata safe to log or display."""

    request_id: str | None
    model: str | None
    duration_seconds: float
    status_category: str


@dataclass(frozen=True)
class ChatResult:
    """Typed result of a chat-completion request."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    reported_cost: float | None
    duration_seconds: float
    request_id: str | None = None
    finish_reason: str | None = None
    usage_available: bool = True

    @property
    def debug_info(self) -> RequestDebugInfo:
        return RequestDebugInfo(
            request_id=self.request_id,
            model=self.model,
            duration_seconds=self.duration_seconds,
            status_category="success",
        )


# --- Status mapping ----------------------------------------------------------

_STATUS_CATEGORY = {
    400: "invalid_request",
    401: "auth_error",
    402: "insufficient_credits",
    429: "rate_limited",
}


def _category_for_status(status: int) -> str:
    if status in _STATUS_CATEGORY:
        return _STATUS_CATEGORY[status]
    if status >= 500:
        return "server_error"
    if 400 <= status < 500:
        return "client_error"
    return "success"


# --- Client ------------------------------------------------------------------


class OpenRouterClient:
    """Non-streaming client for OpenRouter chat completions."""

    def __init__(
        self,
        config: AppConfig,
        *,
        debug: bool = False,
        http_client: httpx.Client | None = None,
        sleeper: "Callable[[float], None] | None" = None,
    ) -> None:
        self._config = config
        self._debug = debug
        # An injected client is used as-is (tests pass a MockTransport client);
        # otherwise a client with explicit timeouts is created lazily.
        self._http = http_client
        self._owns_http = http_client is None
        # Injectable so tests exercise the retry path without real delays.
        self._sleep = sleeper if sleeper is not None else time.sleep

    # -- lifecycle ------------------------------------------------------------

    def _client(self) -> httpx.Client:
        if self._http is None:
            timeout = httpx.Timeout(
                connect=self._config.connect_timeout_seconds,
                read=self._config.read_timeout_seconds,
                write=self._config.read_timeout_seconds,
                pool=self._config.connect_timeout_seconds,
            )
            self._http = httpx.Client(timeout=timeout)
        return self._http

    def close(self) -> None:
        if self._owns_http and self._http is not None:
            self._http.close()
            self._http = None

    def __enter__(self) -> "OpenRouterClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- headers (never logged) ----------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        if not self._config.is_configured or self._config.api_key is None:
            raise MissingAPIKeyError(
                "No OpenRouter API key is configured. Add OPENROUTER_API_KEY to "
                "your environment or Streamlit secrets."
            )
        return {
            "Authorization": f"Bearer {self._config.api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "HTTP-Referer": self._config.app_referer,
            "X-Title": self._config.app_title,
        }

    # -- logging (safe only) --------------------------------------------------

    def _log_debug(self, info: RequestDebugInfo) -> None:
        if self._debug:
            # Only non-sensitive metadata — never headers, keys or content.
            logger.debug(
                "openrouter request id=%s model=%s duration=%.3fs status=%s",
                info.request_id,
                info.model,
                info.duration_seconds,
                info.status_category,
            )

    # -- core request ---------------------------------------------------------

    def create_chat_completion(
        self,
        *,
        model: str,
        messages: Sequence[dict[str, str]],
        temperature: float | None,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
        supported_parameters: Sequence[str] | None = None,
        reasoning: dict[str, Any] | None = None,
        require_parameters: bool = False,
    ) -> ChatResult:
        """Make a single non-streaming chat-completion request.

        Every optional parameter is capability-gated against
        ``supported_parameters`` (from model metadata): a parameter the model
        does not advertise is silently omitted rather than sent and rejected.

        * ``temperature`` is omitted when the model does not support it (many
          reasoning models do not). Pass ``None`` to omit it explicitly.
        * ``response_format`` (a json_object hint or a strict json_schema) is
          only sent when the model advertises ``response_format`` or
          ``structured_outputs``; otherwise :class:`UnsupportedParameterError`
          is raised before any network call.
        * ``reasoning`` is added only when the model advertises ``reasoning``.
        * ``require_parameters`` adds OpenRouter provider routing
          (``provider.require_parameters``) so the request is routed to a
          provider that can satisfy the requested parameters (e.g. strict
          schema) rather than silently degrading.
        """
        # Validate the key up front so a missing key fails clearly and early.
        self._auth_headers()

        payload: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "max_tokens": max_tokens,
            "stream": False,
            # Ask OpenRouter to include cost in the usage block when available.
            "usage": {"include": True},
        }

        # Temperature is capability-gated: omit it for models that do not support
        # it (sending it would be rejected as an unsupported parameter). Live
        # metadata is authoritative when present; without it we fall back to the
        # static MODELS_WITHOUT_TEMPERATURE list so reasoning models never receive
        # a temperature even when metadata was not fetched.
        if supported_parameters is not None:
            temperature_ok = "temperature" in supported_parameters
        else:
            temperature_ok = model not in constants.MODELS_WITHOUT_TEMPERATURE
        if temperature is not None and temperature_ok:
            payload["temperature"] = temperature

        if response_format is not None:
            if supported_parameters is not None and not (
                "response_format" in supported_parameters
                or constants.STRUCTURED_OUTPUT_PARAMETER in supported_parameters
            ):
                raise UnsupportedParameterError(
                    f"Model {model!r} does not support structured output "
                    "(response_format). Choose a different model or technique.",
                    category="unsupported_parameter",
                )
            payload["response_format"] = response_format

        if reasoning is not None and (
            supported_parameters is None or "reasoning" in supported_parameters
        ):
            payload["reasoning"] = reasoning

        if require_parameters:
            # Route to a provider that can actually satisfy the requested
            # parameters (e.g. strict JSON Schema) instead of degrading silently.
            payload["provider"] = {"require_parameters": True}

        return self._post_chat(payload, model)

    def _post_chat(self, payload: dict[str, Any], model: str) -> ChatResult:
        """POST the request, retrying once on a *transient* failure only.

        Transient = a temporary network error, timeout, or one of
        ``TRANSIENT_RETRY_STATUSES`` (429/502/503). These usually produce no
        completion, so a bounded single retry does not multiply billable
        requests. Every other error (400/401/402/403, unsupported parameters,
        schema errors, other 4xx) is raised immediately and never retried.
        """
        headers = self._auth_headers()
        url = self._config.chat_completions_url
        attempts = 1 + constants.MAX_TRANSIENT_RETRIES

        for attempt in range(attempts):
            can_retry = attempt < attempts - 1
            start = time.monotonic()
            try:
                response = self._client().post(url, headers=headers, json=payload)
            except httpx.TimeoutException as exc:
                if can_retry:
                    self._backoff(None)
                    continue
                raise RequestTimeoutError(
                    "The request to OpenRouter timed out. Please try again.",
                    category="timeout",
                ) from exc
            except httpx.RequestError as exc:
                if can_retry:
                    self._backoff(None)
                    continue
                raise NetworkError(
                    "Could not reach OpenRouter due to a network error.",
                    category="network_error",
                ) from exc

            duration = time.monotonic() - start
            if (
                response.status_code in constants.TRANSIENT_RETRY_STATUSES
                and can_retry
            ):
                self._backoff(response.headers.get("retry-after"))
                continue

            # Non-transient status, or the final attempt: map errors and parse.
            self._raise_for_status(response, duration, model)

            try:
                body = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise InvalidResponseError(
                    "OpenRouter returned a response that could not be parsed "
                    "as JSON.",
                    status_code=response.status_code,
                    category="invalid_response",
                ) from exc

            return self._parse_success(body, duration, model)

        # Unreachable: the loop always returns or raises on the final attempt.
        raise NetworkError(
            "Could not reach OpenRouter after retrying.", category="network_error"
        )

    def _backoff(self, retry_after: str | None) -> None:
        """Sleep before a transient retry, honouring ``Retry-After`` when given.

        A provided ``Retry-After`` (seconds) is used but capped, so a hostile or
        very large value cannot block the UI. Otherwise a small base delay plus
        jitter is used to avoid synchronised retries.
        """
        delay = constants.TRANSIENT_RETRY_BASE_DELAY_SECONDS + random.uniform(
            0.0, constants.TRANSIENT_RETRY_BASE_DELAY_SECONDS
        )
        if retry_after is not None:
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                pass
        delay = max(0.0, min(delay, constants.TRANSIENT_RETRY_MAX_DELAY_SECONDS))
        self._sleep(delay)

    def _raise_for_status(
        self, response: httpx.Response, duration: float, model: str
    ) -> None:
        status = response.status_code
        if status < 400:
            return

        category = _category_for_status(status)
        self._log_debug(
            RequestDebugInfo(
                request_id=response.headers.get("x-request-id"),
                model=model,
                duration_seconds=duration,
                status_category=category,
            )
        )
        detail = _safe_error_detail(response)

        if status == 400:
            raise InvalidRequestError(
                f"Invalid request to OpenRouter: {detail}",
                status_code=status,
                category=category,
            )
        if status == 401:
            raise AuthenticationError(
                "OpenRouter rejected the API key (authentication failed).",
                status_code=status,
                category=category,
            )
        if status == 402:
            raise InsufficientCreditsError(
                "The OpenRouter account has insufficient credits for this request.",
                status_code=status,
                category=category,
            )
        if status == 429:
            raise RateLimitError(
                "OpenRouter rate limit reached. Please wait and try again.",
                status_code=status,
                category=category,
            )
        if status >= 500:
            raise ServerError(
                "OpenRouter or the upstream model returned a server error.",
                status_code=status,
                category=category,
            )
        raise OpenRouterError(
            f"OpenRouter request failed ({status}): {detail}",
            status_code=status,
            category=category,
        )

    def _parse_success(
        self, body: dict[str, Any], duration: float, model: str
    ) -> ChatResult:
        request_id = body.get("id")
        actual_model = body.get("model") or model

        choices = body.get("choices")
        if not choices:
            # A genuinely malformed response — no choices at all.
            raise InvalidResponseError(
                "OpenRouter returned no choices in the response.",
                category="invalid_response",
            )
        first_choice = choices[0] or {}
        message = first_choice.get("message") or {}
        content = message.get("content")
        finish_reason = first_choice.get("finish_reason")

        if content is None or (isinstance(content, str) and not content.strip()):
            # Valid HTTP response but no visible text. Distinguish a provider
            # error (do not retry) from a genuine empty generation (retryable
            # for the connection test only).
            provider_detail = _provider_error_detail(body, first_choice)
            if provider_detail is not None:
                raise ProviderError(
                    f"The model provider reported an error: {provider_detail}",
                    category="provider_error",
                )
            raise EmptyContentError(
                "OpenRouter response contained no assistant content "
                f"(finish_reason: {finish_reason or 'unknown'}).",
                category="empty_content",
            )

        usage = body.get("usage")
        if not usage:
            # Content is usable, but token accounting is unavailable. Degrade
            # gracefully rather than failing the whole request.
            result = ChatResult(
                content=content,
                model=actual_model,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                reported_cost=None,
                duration_seconds=duration,
                request_id=request_id,
                finish_reason=finish_reason,
                usage_available=False,
            )
            self._log_debug(result.debug_info)
            return result

        prompt_tokens = int(usage.get("prompt_tokens", 0) or 0)
        completion_tokens = int(usage.get("completion_tokens", 0) or 0)
        total_tokens = int(
            usage.get("total_tokens", prompt_tokens + completion_tokens) or 0
        )
        reported_cost = usage.get("cost")
        reported_cost = float(reported_cost) if reported_cost is not None else None

        result = ChatResult(
            content=content,
            model=actual_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            reported_cost=reported_cost,
            duration_seconds=duration,
            request_id=request_id,
            finish_reason=finish_reason,
            usage_available=True,
        )
        self._log_debug(result.debug_info)
        return result

    # -- connection test ------------------------------------------------------

    def test_connection(
        self, supported_parameters: Sequence[str] | None = None
    ) -> ChatResult:
        """Make a small request to verify connectivity, auth and visible output.

        Intended to run only when the user presses a "Test connection" button.
        It proves authentication works, the selected model is reachable, and the
        model can return visible text.

        Reasoning models (e.g. GPT-5) can spend the whole output budget on
        internal reasoning before emitting content, so the test asks for the
        **minimal** reasoning allocation and excludes reasoning from the output
        (``{"effort": "minimal", "exclude": True}``). This is sent only when the
        model's ``supported_parameters`` advertise ``reasoning`` (or when
        metadata is unavailable); otherwise it is omitted. A modest 256-token
        budget gives headroom either way.

        Because a reasoning model can still occasionally return an empty
        (no-text) generation, the connection test — and *only* the connection
        test — retries once on :class:`EmptyContentError`. Authentication (401),
        credit (402), rate-limit (429) and provider errors are never retried.
        """
        messages = [{"role": "user", "content": constants.CONNECTION_TEST_PROMPT}]
        reasoning = {"effort": "minimal", "exclude": True}
        attempts = constants.CONNECTION_TEST_MAX_RETRIES + 1
        for attempt in range(attempts):
            try:
                return self.create_chat_completion(
                    model=self._config.model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=constants.CONNECTION_TEST_MAX_TOKENS,
                    supported_parameters=supported_parameters,
                    reasoning=reasoning,
                )
            except EmptyContentError:
                # Retry once (last attempt falls through to the controlled error).
                if attempt >= attempts - 1:
                    break
        raise EmptyContentError(
            "OpenRouter connected successfully, but the selected model returned "
            "no text. Please retry once or try another model.",
            category="empty_content",
        )


def _provider_error_detail(body: dict[str, Any], choice: dict[str, Any]) -> str | None:
    """Return a short, safe provider-error message if one is present, else None.

    OpenRouter can return a 2xx response that still carries a provider error at
    the top level or on the choice. Never returns headers or credentials.
    """
    for source in (choice, body):
        error = source.get("error") if isinstance(source, dict) else None
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:200]
        if isinstance(error, str) and error.strip():
            return error[:200]
    return None


def _safe_error_detail(response: httpx.Response) -> str:
    """Extract a short, safe error message from an error response body.

    Never returns headers or credentials; falls back to a generic phrase.
    """
    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        return "no additional detail"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:200]
        if isinstance(error, str):
            return error[:200]
    return "no additional detail"
