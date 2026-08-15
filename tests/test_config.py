"""Tests for configuration loading and central constants.

No live API calls are made anywhere in the test suite.
"""

import pytest

from src import constants
from src.config import API_KEY_NAME, AppConfig, load_config


class TestConstants:
    """The approved models and safe defaults are defined centrally."""

    def test_default_model_is_gpt_5_mini(self) -> None:
        assert constants.DEFAULT_MODEL == "openai/gpt-5-mini"

    def test_all_three_approved_models_are_defined(self) -> None:
        assert set(constants.APPROVED_MODELS) == {
            "openai/gpt-5-mini",
            "openai/gpt-5-nano",
            "openai/gpt-5",
        }

    def test_default_model_is_approved(self) -> None:
        assert constants.DEFAULT_MODEL in constants.APPROVED_MODELS

    def test_temperature_defaults_are_within_bounds(self) -> None:
        assert (
            constants.MIN_TEMPERATURE
            <= constants.DEFAULT_TEMPERATURE
            <= constants.MAX_TEMPERATURE
        )

    def test_output_token_defaults_are_within_bounds(self) -> None:
        assert (
            constants.MIN_OUTPUT_TOKENS
            <= constants.DEFAULT_MAX_OUTPUT_TOKENS
            <= constants.MAX_OUTPUT_TOKENS_LIMIT
        )

    def test_input_limits_are_positive(self) -> None:
        assert constants.MAX_JOB_DESCRIPTION_CHARS > 0
        assert constants.MAX_CANDIDATE_BACKGROUND_CHARS > 0
        assert constants.MAX_ANSWER_CHARS > 0


class TestLoadConfig:
    """Configuration loading is controlled and never crashes on a missing key."""

    @pytest.fixture(autouse=True)
    def _isolate_from_local_secrets(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep these tests hermetic.

        A developer's machine may have a real key in ``.streamlit/secrets.toml``
        or a ``.env`` file. These tests exercise the environment-variable path,
        so the Streamlit-secret lookup and ``.env`` loading are neutralised to
        avoid reading (or depending on) a real local key.
        """
        monkeypatch.setattr("src.config._read_streamlit_secret", lambda: None)
        monkeypatch.setattr("src.config.load_dotenv", lambda *a, **k: None)

    def test_missing_key_returns_unconfigured_result(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(API_KEY_NAME, raising=False)
        config = load_config()
        assert config.is_configured is False
        assert config.api_key is None

    def test_environment_variable_is_used_as_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(API_KEY_NAME, "test-key-not-real")
        config = load_config()
        assert config.is_configured is True
        assert config.api_key is not None
        assert config.api_key.get_secret_value() == "test-key-not-real"

    def test_whitespace_only_key_counts_as_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(API_KEY_NAME, "   ")
        config = load_config()
        assert config.is_configured is False

    def test_defaults_come_from_constants(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv(API_KEY_NAME, raising=False)
        config = load_config()
        assert config.model == constants.DEFAULT_MODEL
        assert config.temperature == constants.DEFAULT_TEMPERATURE
        assert config.max_output_tokens == constants.DEFAULT_MAX_OUTPUT_TOKENS

    def test_speech_unconfigured_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.config._read_setting", lambda name: None)
        monkeypatch.setenv(API_KEY_NAME, "test-key-not-real")
        config = load_config()
        # Text interview still works even though speech is not configured.
        assert config.is_configured is True
        assert config.is_speech_configured is False
        assert config.google_speech_project_id is None

    def test_speech_configured_from_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.config._read_setting",
            lambda name: "gcp-proj" if name.endswith("PROJECT_ID") else None,
        )
        monkeypatch.delenv(API_KEY_NAME, raising=False)
        config = load_config()
        assert config.is_speech_configured is True
        assert config.google_speech_project_id == "gcp-proj"
        assert config.google_speech_location == constants.SPEECH_LOCATION_DEFAULT

    def test_live_unconfigured_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.config._read_setting", lambda name: None)
        monkeypatch.delenv(API_KEY_NAME, raising=False)
        config = load_config()
        assert config.is_live_configured is False
        assert config.gemini_api_key is None

    def test_live_configured_from_gemini_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "src.config._read_setting",
            lambda name: "gemini-secret" if name == "GEMINI_API_KEY" else None,
        )
        monkeypatch.delenv(API_KEY_NAME, raising=False)
        config = load_config()
        assert config.is_live_configured is True
        # The Gemini key is masked if the config is printed/logged.
        assert "gemini-secret" not in repr(config)
        assert "gemini-secret" not in str(config)

    def test_auth_and_database_defaults(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("src.config._read_setting", lambda name: None)
        monkeypatch.delenv(API_KEY_NAME, raising=False)
        config = load_config()
        # Local development: auth optional, SQLite database.
        assert config.auth_required is False
        assert config.database_url == constants.DEFAULT_DATABASE_URL

    def test_auth_required_and_database_from_settings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        values = {
            "APP_AUTH_REQUIRED": "true",
            "DATABASE_URL": "postgresql://example/db",
        }
        monkeypatch.setattr("src.config._read_setting", lambda name: values.get(name))
        monkeypatch.delenv(API_KEY_NAME, raising=False)
        config = load_config()
        assert config.auth_required is True
        assert config.database_url == "postgresql://example/db"


class TestSecretSafety:
    """The API key must never leak through printing or logging."""

    def test_api_key_is_masked_in_repr_and_str(self) -> None:
        config = AppConfig.model_validate({"api_key": "super-secret-value"})
        assert "super-secret-value" not in repr(config)
        assert "super-secret-value" not in str(config)

    def test_no_default_api_key_exists(self) -> None:
        config = AppConfig()
        assert config.api_key is None
        assert config.is_configured is False
