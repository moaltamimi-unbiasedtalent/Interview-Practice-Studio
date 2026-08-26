"""OS-3 tests: the consolidated shared core (infrastructure only)."""

import logging

import pytest

from src.core import secrets as core_secrets
from src.core.config import AppConfig, OpenRouterCredentials, load_app_config
from src.core.errors import ConfigError, InterviewOSError, SafeError
from src.core.logging import SENSITIVE_KEYS, safe_extra
from src.core.security import count_control_chars, strip_zero_width
from src.core.usage import Operation, UsageLedger, UsageRecord


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic: no Streamlit secrets, no .env; only env vars we set count."""
    monkeypatch.setattr("src.core.secrets.read_streamlit", lambda name: None)
    monkeypatch.setattr("src.core.secrets.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("src.config.load_dotenv", lambda *a, **k: None)
    monkeypatch.setattr("src.copilot.config.load_dotenv", lambda *a, **k: None)
    for name in (
        "OPENROUTER_API_KEY",
        "GOOGLE_SPEECH_PROJECT_ID",
        "GEMINI_API_KEY",
        "COPILOT_EMBEDDING_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


# --- Shared configuration ----------------------------------------------------


class TestSharedConfig:
    def test_composed_config_has_three_sections(self) -> None:
        config = load_app_config()
        assert isinstance(config, AppConfig)
        assert isinstance(config.openrouter, OpenRouterCredentials)
        assert config.career is not None and config.interview is not None

    def test_missing_key_is_unconfigured_everywhere(self) -> None:
        config = load_app_config()
        assert config.is_configured is False
        assert config.career.is_configured is False
        assert config.interview.is_configured is False

    def test_one_openrouter_key_is_shared_across_modules(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "shared-key-not-real")
        config = load_app_config()
        assert config.is_configured is True
        assert config.career.is_configured is True
        assert config.interview.is_configured is True
        key = "shared-key-not-real"
        assert config.openrouter.api_key.get_secret_value() == key
        assert config.career.api_key.get_secret_value() == key
        assert config.interview.api_key.get_secret_value() == key

    def test_missing_career_config_uses_safe_defaults(self) -> None:
        # No embedding key -> career still usable; embedder falls back to local.
        from src.copilot.embeddings import build_embedder

        config = load_app_config()
        assert config.career.embedding_key is None
        assert build_embedder(config.career).provider == "local"

    def test_missing_interview_optional_config(self) -> None:
        config = load_app_config()
        assert config.is_speech_configured is False
        assert config.is_live_configured is False

    def test_secret_is_masked_in_repr(self, monkeypatch) -> None:
        monkeypatch.setenv("OPENROUTER_API_KEY", "top-secret-value")
        config = load_app_config()
        assert "top-secret-value" not in repr(config)
        assert "top-secret-value" not in str(config)

    def test_shared_reader_precedence_streamlit_over_env(self, monkeypatch) -> None:
        monkeypatch.setattr("src.core.secrets.read_streamlit", lambda name: "from-secrets")
        monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
        assert core_secrets.read_setting("OPENROUTER_API_KEY") == "from-secrets"


# --- Usage isolation ---------------------------------------------------------


class TestUsage:
    def test_sources_are_isolated_and_summed(self) -> None:
        ledger = UsageLedger()
        ledger.add(UsageRecord(operation=Operation.CAREER_FINAL_GENERATION, total_tokens=100, id="a"))
        ledger.add(UsageRecord(operation=Operation.INTERVIEW_EVALUATION, total_tokens=40, id="b"))
        ledger.add(UsageRecord(operation=Operation.CAREER_TOOLS, total_tokens=10, id="c"))
        by_source = ledger.tokens_by_source()
        assert by_source["career_final_generation"] == 100
        assert by_source["interview_evaluation"] == 40
        assert ledger.total_tokens == 150

    def test_no_double_counting(self) -> None:
        ledger = UsageLedger()
        record = UsageRecord(operation=Operation.INTERVIEW_STRATEGY, total_tokens=25, id="dup")
        assert ledger.add(record) is True
        assert ledger.add(record) is False  # same id ignored
        assert ledger.total_tokens == 25
        assert len(ledger.records) == 1


# --- Safe logging ------------------------------------------------------------


class TestSafeLogging:
    def test_safe_extra_redacts_sensitive_fields(self) -> None:
        safe = safe_extra(
            job_description="secret jd",
            candidate_background="secret cv",
            api_key="sk-xxx",
            content="model said...",
            count=3,
            model="openai/gpt-5-mini",
        )
        assert safe["job_description"] == "[REDACTED]"
        assert safe["candidate_background"] == "[REDACTED]"
        assert safe["api_key"] == "[REDACTED]"
        assert safe["content"] == "[REDACTED]"
        assert safe["count"] == 3  # safe metadata preserved
        assert safe["model"] == "openai/gpt-5-mini"

    def test_sensitive_keys_cover_the_forbidden_set(self) -> None:
        for key in ("candidate_background", "job_description", "transcript", "chunks", "response"):
            assert key in SENSITIVE_KEYS


# --- Security primitives -----------------------------------------------------


class TestSecurityPrimitives:
    def test_count_control_chars(self) -> None:
        assert count_control_chars("a\x00b​c") >= 2

    def test_strip_zero_width(self) -> None:
        assert strip_zero_width("a​b‎c") == "abc"


# --- Errors ------------------------------------------------------------------


class TestErrors:
    def test_hierarchy(self) -> None:
        assert issubclass(ConfigError, InterviewOSError)
        assert issubclass(SafeError, InterviewOSError)

    def test_safe_error_hides_detail(self) -> None:
        err = SafeError("Something went wrong.", detail="secret stacktrace")
        assert err.user_message == "Something went wrong."
        assert err.detail == "secret stacktrace"
        assert "secret stacktrace" not in str(err)
