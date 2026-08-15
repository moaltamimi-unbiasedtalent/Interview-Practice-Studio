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
SPEECH_PROJECT_NAME = "GOOGLE_SPEECH_PROJECT_ID"
SPEECH_LOCATION_NAME = "GOOGLE_SPEECH_LOCATION"
GEMINI_API_KEY_NAME = "GEMINI_API_KEY"
GEMINI_MODEL_NAME = "GEMINI_LIVE_MODEL"
AUTH_REQUIRED_NAME = "APP_AUTH_REQUIRED"
DATABASE_URL_NAME = "DATABASE_URL"


def _read_bool(name: str, default: bool = False) -> bool:
    raw = _read_setting(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


class AppConfig(BaseModel):
    """Runtime configuration for the application.

    The API key is stored as a ``SecretStr`` so it is masked if the object is
    ever printed or logged.
    """

    api_key: SecretStr | None = None
    model: str = constants.DEFAULT_MODEL
    temperature: float = constants.DEFAULT_TEMPERATURE
    max_output_tokens: int = constants.DEFAULT_MAX_OUTPUT_TOKENS

    # Speech-to-text (optional). Only the non-secret project/location are stored;
    # credentials themselves come from Google Application Default Credentials
    # (e.g. GOOGLE_APPLICATION_CREDENTIALS) and are never read or stored here.
    google_speech_project_id: str | None = None
    google_speech_location: str = constants.SPEECH_LOCATION_DEFAULT

    # Live interview (optional). The permanent Gemini key is a secret used only
    # on the backend to mint short-lived ephemeral tokens; it is never sent to
    # the browser. Stored as SecretStr so it is masked if printed or logged.
    gemini_api_key: SecretStr | None = None
    gemini_live_model: str = constants.LIVE_INTERVIEW_MODEL

    # Accounts & persistence. Auth is optional for local development and
    # required in production. The database URL selects SQLite (dev) or
    # PostgreSQL (prod); it is configuration, not a secret credential store.
    auth_required: bool = False
    database_url: str = constants.DEFAULT_DATABASE_URL

    # OpenRouter connection settings (defaults from constants). These are not
    # secrets and are safe to display or log.
    base_url: str = constants.OPENROUTER_BASE_URL
    connect_timeout_seconds: float = constants.CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = constants.READ_TIMEOUT_SECONDS
    app_referer: str = constants.OPENROUTER_APP_REFERER
    app_title: str = constants.OPENROUTER_APP_TITLE

    @property
    def is_configured(self) -> bool:
        """Return ``True`` when a non-empty API key is available."""
        return (
            self.api_key is not None
            and self.api_key.get_secret_value().strip() != ""
        )

    @property
    def is_speech_configured(self) -> bool:
        """Return ``True`` when a speech project is set (voice answers enabled).

        This gates the feature on a configured Google project; credentials are
        resolved separately via Application Default Credentials, and a genuine
        auth failure surfaces as a controlled error at transcription time.
        """
        return bool(self.google_speech_project_id)

    @property
    def is_live_configured(self) -> bool:
        """Return ``True`` when a Gemini key is available (live mode enabled)."""
        return (
            self.gemini_api_key is not None
            and self.gemini_api_key.get_secret_value().strip() != ""
        )

    @property
    def chat_completions_url(self) -> str:
        """Full URL of the OpenRouter chat-completions endpoint."""
        return f"{self.base_url.rstrip('/')}{constants.OPENROUTER_CHAT_COMPLETIONS_PATH}"

    @property
    def models_url(self) -> str:
        """Full URL of the OpenRouter models-metadata endpoint."""
        return f"{self.base_url.rstrip('/')}{constants.OPENROUTER_MODELS_PATH}"


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


def _read_setting(name: str) -> str | None:
    """Read a non-secret setting from Streamlit secrets, then the environment.

    Used for values that are configuration (not credentials), such as the
    Google Cloud project id and location for speech-to-text.
    """
    try:
        import streamlit as st

        value = st.secrets.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    except Exception:
        pass
    env_value = os.environ.get(name)
    if env_value and env_value.strip():
        return env_value.strip()
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

    speech_project = _read_setting(SPEECH_PROJECT_NAME)
    speech_location = _read_setting(SPEECH_LOCATION_NAME) or constants.SPEECH_LOCATION_DEFAULT

    # The Gemini key is read from secrets first, then the environment, and wrapped
    # in SecretStr so it is masked if the config is ever printed or logged.
    raw_gemini = _read_setting(GEMINI_API_KEY_NAME)
    gemini_api_key = SecretStr(raw_gemini) if raw_gemini else None
    gemini_model = _read_setting(GEMINI_MODEL_NAME) or constants.LIVE_INTERVIEW_MODEL

    return AppConfig(
        api_key=api_key,
        google_speech_project_id=speech_project,
        google_speech_location=speech_location,
        gemini_api_key=gemini_api_key,
        gemini_live_model=gemini_model,
        auth_required=_read_bool(AUTH_REQUIRED_NAME, default=False),
        database_url=_read_setting(DATABASE_URL_NAME) or constants.DEFAULT_DATABASE_URL,
    )
