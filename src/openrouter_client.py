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
import time
from collections.abc import Sequence
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
    ) -> None:
        self._config = config
        self._debug = debug
        # An injected client is used as-is (tests pass a MockTransport client);
        # otherwise a client with explicit timeouts is created lazily.
        self._http = http_client
        self._owns_http = http_client is None

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
        temperature: float,
        max_tokens: int,
        response_format: dict[str, Any] | None = None,
        supported_parameters: Sequence[str] | None = None,
    ) -> ChatResult:
        """Make a single non-streaming chat-completion request.

        ``response_format`` (structured output) is only sent when the model is
        known to support it. If it is requested for a model whose
        ``supported_parameters`` do not include ``response_format``, an
        :class:`UnsupportedParameterError` is raised before any network call.
        """
        # Validate the key up front so a missing key fails clearly and early.
        self._auth_headers()

        payload: dict[str, Any] = {
            "model": model,
            "messages": list(messages),
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            # Ask OpenRouter to include cost in the usage block when available.
            "usage": {"include": True},
        }

        if response_format is not None:
            if (
                supported_parameters is not None
                and "response_format" not in supported_parameters
            ):
                raise UnsupportedParameterError(
                    f"Model {model!r} does not support structured output "
                    "(response_format). Choose a different model or technique.",
                    category="unsupported_parameter",
                )
            payload["response_format"] = response_format

        return self._post_chat(payload, model)

    def _post_chat(self, payload: dict[str, Any], model: str) -> ChatResult:
        headers = self._auth_headers()
        url = self._config.chat_completions_url
        start = time.monotonic()

        try:
            response = self._client().post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            raise RequestTimeoutError(
                "The request to OpenRouter timed out. Please try again.",
                category="timeout",
            ) from exc
        except httpx.RequestError as exc:
            raise NetworkError(
                "Could not reach OpenRouter due to a network error.",
                category="network_error",
            ) from exc

        duration = time.monotonic() - start
        self._raise_for_status(response, duration, model)

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as exc:
            raise InvalidResponseError(
                "OpenRouter returned a response that could not be parsed as JSON.",
                status_code=response.status_code,
                category="invalid_response",
            ) from exc

        return self._parse_success(body, duration, model)

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
            raise InvalidResponseError(
                "OpenRouter returned no choices in the response.",
                category="invalid_response",
            )
        message = (choices[0] or {}).get("message") or {}
        content = message.get("content")
        finish_reason = (choices[0] or {}).get("finish_reason")
        if content is None:
            raise InvalidResponseError(
                "OpenRouter response contained no assistant content.",
                category="invalid_response",
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

    def test_connection(self) -> ChatResult:
        """Make a tiny request to verify connectivity and authentication.

        Intended to run only when the user presses a "Test connection" button —
        it is a real (but minimal) request that consumes a few tokens.
        """
        return self.create_chat_completion(
            model=self._config.model,
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            max_tokens=constants.CONNECTION_TEST_MAX_TOKENS,
        )


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
