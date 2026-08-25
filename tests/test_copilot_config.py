"""Foundation tests for Career Intelligence Copilot configuration."""

import pytest
from pydantic import SecretStr

from src.copilot import constants
from src.copilot.config import API_KEY_NAME, CopilotConfig, load_config


class TestLoadConfig:
    @pytest.fixture(autouse=True)
    def _isolate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Hermetic: no real secrets file or .env influences these tests.
        monkeypatch.setattr("src.copilot.config.load_dotenv", lambda *a, **k: None)
        monkeypatch.setattr("src.copilot.config._read_streamlit", lambda name: None)

    def test_missing_key_is_unconfigured(self, monkeypatch) -> None:
        monkeypatch.setattr("src.copilot.config._read_env", lambda name: None)
        config = load_config()
        assert config.is_configured is False
        assert config.api_key is None

    def test_env_key_is_used(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.copilot.config._read_env",
            lambda name: "test-key-not-real" if name == API_KEY_NAME else None,
        )
        config = load_config()
        assert config.is_configured is True
        assert config.api_key.get_secret_value() == "test-key-not-real"

    def test_whitespace_key_counts_as_missing(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "src.copilot.config._read_env",
            lambda name: "   " if name == API_KEY_NAME else None,
        )
        assert load_config().is_configured is False

    def test_defaults_come_from_constants(self, monkeypatch) -> None:
        monkeypatch.setattr("src.copilot.config._read_env", lambda name: None)
        config = load_config()
        assert config.default_model == constants.DEFAULT_MODEL
        assert config.base_url == constants.OPENROUTER_BASE_URL
        assert config.chroma_persist_dir == constants.CHROMA_PERSIST_DIR
        assert config.embedding_model == constants.DEFAULT_EMBEDDING_MODEL


class TestSecretSafety:
    def test_key_is_masked_in_repr_and_str(self) -> None:
        config = CopilotConfig(api_key=SecretStr("super-secret-value"))
        assert "super-secret-value" not in repr(config)
        assert "super-secret-value" not in str(config)

    def test_embedding_key_falls_back_to_api_key(self) -> None:
        config = CopilotConfig(api_key=SecretStr("k"))
        assert config.embedding_key is config.api_key

    def test_separate_embedding_key_takes_precedence(self) -> None:
        config = CopilotConfig(
            api_key=SecretStr("k"), embedding_api_key=SecretStr("e")
        )
        assert config.embedding_key.get_secret_value() == "e"
