"""One composed application configuration for Interview OS Coach.

`AppConfig` groups the platform's configuration into three sections:

* ``openrouter`` — shared OpenRouter credentials/settings (one API key).
* ``career``     — the Career Intelligence config (embeddings, Chroma, retrieval).
* ``interview``  — the Interview Practice config (Google Speech, Gemini Live, db).

All three resolve secrets through :mod:`src.core.secrets` (Streamlit → env, no
default keys, ``SecretStr`` masking), so the OpenRouter key comes from a single
place. This does **not** merge the two AI workflows — Career keeps LangChain,
Interview keeps its direct client; only the credentials/config are shared.
"""

from __future__ import annotations

from pydantic import BaseModel, SecretStr

from src.config import AppConfig as InterviewConfig
from src.config import load_config as _load_interview
from src.copilot import constants as _career_constants
from src.copilot.config import CopilotConfig
from src.copilot.config import load_config as _load_career
from src.core import secrets as _secrets

__all__ = ["OpenRouterCredentials", "AppConfig", "load_app_config"]

_OPENROUTER_KEY = "OPENROUTER_API_KEY"


class OpenRouterCredentials(BaseModel):
    """Shared OpenRouter credentials and connection settings.

    Both modules read the same key; Career wraps it in a LangChain ChatOpenAI
    factory and Interview in a direct HTTPX client (see the architecture doc).
    """

    api_key: SecretStr | None = None
    base_url: str = _career_constants.OPENROUTER_BASE_URL
    model: str = _career_constants.DEFAULT_MODEL
    connect_timeout_seconds: float = _career_constants.CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = _career_constants.READ_TIMEOUT_SECONDS

    @property
    def is_configured(self) -> bool:
        return (
            self.api_key is not None
            and self.api_key.get_secret_value().strip() != ""
        )


class AppConfig(BaseModel):
    """The single composed platform configuration."""

    openrouter: OpenRouterCredentials
    career: CopilotConfig
    interview: InterviewConfig

    @property
    def is_configured(self) -> bool:
        """True when the shared OpenRouter key is available."""
        return self.openrouter.is_configured

    @property
    def is_speech_configured(self) -> bool:
        return self.interview.is_speech_configured

    @property
    def is_live_configured(self) -> bool:
        return self.interview.is_live_configured


def load_app_config() -> AppConfig:
    """Build the composed configuration; never raises on a missing key."""
    _secrets.load_dotenv_once()
    shared_key = _secrets.read_secret(_OPENROUTER_KEY)
    # Both sub-configs resolve the same OpenRouter key via src.core.secrets.
    career = _load_career()
    interview = _load_interview()
    openrouter = OpenRouterCredentials(
        api_key=shared_key,
        base_url=career.base_url,
        model=career.default_model,
    )
    return AppConfig(openrouter=openrouter, career=career, interview=interview)
