"""LangChain-compatible OpenRouter chat model factory.

OpenRouter is used via its OpenAI-compatible API, so we configure LangChain's
``ChatOpenAI`` with OpenRouter's base URL and key rather than duplicating an HTTP
client. LangChain is imported lazily so importing this module never requires the
package, and tests can run without hitting the network.

Guarantees: explicit model selection, explicit timeout, controlled errors, and
no secret logging (the key is read from ``SecretStr`` only at call time and
passed straight to the client).
"""

from __future__ import annotations

from typing import Any

from src.copilot import constants
from src.copilot.config import CopilotConfig

__all__ = ["CopilotConfigError", "build_chat_model", "default_model_kwargs"]


class CopilotConfigError(Exception):
    """Raised when the LLM cannot be built because configuration is missing."""


def default_model_kwargs(
    config: CopilotConfig,
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """Resolve the keyword arguments for the chat model (no secrets included)."""
    return {
        "model": model or config.default_model,
        "temperature": (
            temperature if temperature is not None else constants.DEFAULT_TEMPERATURE
        ),
        "max_tokens": max_tokens or constants.DEFAULT_MAX_OUTPUT_TOKENS,
        "base_url": config.base_url,
        "timeout": config.read_timeout_seconds,
        "max_retries": constants.LLM_MAX_RETRIES,
    }


def build_chat_model(
    config: CopilotConfig,
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    chat_openai_cls: Any | None = None,
):
    """Return a configured LangChain chat model backed by OpenRouter.

    ``chat_openai_cls`` can be injected in tests to avoid importing the SDK or
    making network calls. Raises :class:`CopilotConfigError` when no API key is
    configured — never returns a model that would fail opaquely later.
    """
    if not config.is_configured or config.api_key is None:
        raise CopilotConfigError(
            "No OpenRouter API key is configured. Add OPENROUTER_API_KEY to your "
            "environment or Streamlit secrets."
        )

    if chat_openai_cls is None:
        try:  # Lazy import so the module loads without langchain-openai present.
            from langchain_openai import ChatOpenAI as chat_openai_cls  # type: ignore
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise CopilotConfigError(
                "langchain-openai is not installed. Install the project "
                "dependencies to use the OpenRouter chat model."
            ) from exc

    kwargs = default_model_kwargs(
        config, model=model, temperature=temperature, max_tokens=max_tokens
    )
    # The key is passed straight to the client and never logged.
    return chat_openai_cls(
        api_key=config.api_key.get_secret_value(),
        default_headers={
            "HTTP-Referer": config.app_referer,
            "X-Title": config.app_title,
        },
        **kwargs,
    )
