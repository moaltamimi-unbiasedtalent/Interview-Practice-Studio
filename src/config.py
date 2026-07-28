"""Application configuration loading.

The OpenRouter API key is resolved in this order:

1. Streamlit secrets (``.streamlit/secrets.toml``) — preferred.
2. The ``OPENROUTER_API_KEY`` environment variable — local development
   fallback only (optionally populated from a ``.env`` file).

There is never a default key. A missing key produces a controlled
``AppConfig`` with ``is_configured`` set to ``False`` instead of an exception,
so the UI can show a friendly message rather than crash.
"""

import os

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr

from src import constants

API_KEY_NAME = "OPENROUTER_API_KEY"


class AppConfig(BaseModel):
    """Runtime configuration for the application.

    The API key is stored as a ``SecretStr`` so it is masked if the object is
    ever printed or logged.
    """

    api_key: SecretStr | None = None
    model: str = constants.DEFAULT_MODEL
    temperature: float = constants.DEFAULT_TEMPERATURE
    max_output_tokens: int = constants.DEFAULT_MAX_OUTPUT_TOKENS

    @property
    def is_configured(self) -> bool:
        """Return ``True`` when a non-empty API key is available."""
        return (
            self.api_key is not None
            and self.api_key.get_secret_value().strip() != ""
        )


def _read_streamlit_secret() -> str | None:
    """Read the API key from Streamlit secrets, if available.

    Streamlit raises an error when no secrets file exists at all. That is an
    expected situation in local development and in tests, so it is treated as
    "no secret configured" rather than an application failure.
    """
    try:
        import streamlit as st

        value = st.secrets.get(API_KEY_NAME)
    except Exception:
        # Expected when no secrets.toml exists or Streamlit is not running.
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_environment_secret() -> str | None:
    """Read the API key from the environment (local development fallback)."""
    value = os.environ.get(API_KEY_NAME)
    if value and value.strip():
        return value.strip()
    return None


def load_config() -> AppConfig:
    """Build the application configuration.

    Loads ``.env`` for local development (never overriding real environment
    variables), then resolves the API key with Streamlit secrets taking
    priority over the environment. Never raises on a missing key.
    """
    load_dotenv(override=False)
    raw_key = _read_streamlit_secret() or _read_environment_secret()
    api_key = SecretStr(raw_key) if raw_key else None
    return AppConfig(api_key=api_key)
