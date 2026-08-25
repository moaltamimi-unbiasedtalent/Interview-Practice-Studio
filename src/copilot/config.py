"""Configuration loading for Career Intelligence Copilot.

Secrets are resolved from Streamlit secrets first, then environment variables.
There is never a default API key: a missing key yields a controlled unconfigured
config (``is_configured == False``) rather than an exception, so the UI can show
a friendly message. The key is stored as ``SecretStr`` so it is masked if the
config is ever printed or logged.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr

from src.copilot import constants

__all__ = ["CopilotConfig", "load_config"]

API_KEY_NAME = "OPENROUTER_API_KEY"
BASE_URL_NAME = "OPENROUTER_BASE_URL"
MODEL_NAME = "COPILOT_MODEL"
EMBEDDING_MODEL_NAME = "COPILOT_EMBEDDING_MODEL"
EMBEDDING_BASE_URL_NAME = "COPILOT_EMBEDDING_BASE_URL"
EMBEDDING_KEY_NAME = "COPILOT_EMBEDDING_API_KEY"
CHROMA_DIR_NAME = "COPILOT_CHROMA_DIR"
DEBUG_NAME = "COPILOT_DEBUG"


class CopilotConfig(BaseModel):
    """Runtime configuration. The API key is masked via ``SecretStr``."""

    api_key: SecretStr | None = None
    base_url: str = constants.OPENROUTER_BASE_URL
    default_model: str = constants.DEFAULT_MODEL

    # Embeddings (used from Phase 2; kept as config now). A separate optional key
    # allows a different embeddings provider from the chat provider.
    embedding_model: str = constants.DEFAULT_EMBEDDING_MODEL
    embedding_base_url: str = constants.DEFAULT_EMBEDDING_BASE_URL
    embedding_api_key: SecretStr | None = None

    # Vector store persistence.
    chroma_persist_dir: str = constants.CHROMA_PERSIST_DIR

    # Connection + development settings.
    connect_timeout_seconds: float = constants.CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = constants.READ_TIMEOUT_SECONDS
    app_referer: str = constants.OPENROUTER_APP_REFERER
    app_title: str = constants.OPENROUTER_APP_TITLE
    debug: bool = False

    @property
    def is_configured(self) -> bool:
        """True when a non-empty OpenRouter API key is available."""
        return (
            self.api_key is not None
            and self.api_key.get_secret_value().strip() != ""
        )

    @property
    def embedding_key(self) -> SecretStr | None:
        """Embedding key if set, else the OpenRouter key (same-provider default)."""
        return self.embedding_api_key or self.api_key


def _read_streamlit(name: str) -> str | None:
    """Read a value from Streamlit secrets, tolerating no-secrets environments."""
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _read_env(name: str) -> str | None:
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def _read(name: str) -> str | None:
    """Streamlit secrets take precedence over environment variables."""
    return _read_streamlit(name) or _read_env(name)


def _read_bool(name: str, default: bool = False) -> bool:
    raw = _read(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def load_config() -> CopilotConfig:
    """Build the configuration from secrets/environment; never raises on a
    missing key."""
    load_dotenv(override=False)
    raw_key = _read(API_KEY_NAME)
    raw_embed_key = _read(EMBEDDING_KEY_NAME)
    return CopilotConfig(
        api_key=SecretStr(raw_key) if raw_key else None,
        base_url=_read(BASE_URL_NAME) or constants.OPENROUTER_BASE_URL,
        default_model=_read(MODEL_NAME) or constants.DEFAULT_MODEL,
        embedding_model=_read(EMBEDDING_MODEL_NAME)
        or constants.DEFAULT_EMBEDDING_MODEL,
        embedding_base_url=_read(EMBEDDING_BASE_URL_NAME)
        or constants.DEFAULT_EMBEDDING_BASE_URL,
        embedding_api_key=SecretStr(raw_embed_key) if raw_embed_key else None,
        chroma_persist_dir=_read(CHROMA_DIR_NAME) or constants.CHROMA_PERSIST_DIR,
        debug=_read_bool(DEBUG_NAME, default=False),
    )
