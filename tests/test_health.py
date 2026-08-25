"""Tests for startup validation and the health check."""

from pydantic import SecretStr

from src import health
from src.config import AppConfig


def _cfg(**over) -> AppConfig:
    base = dict(database_url="sqlite:///data/x.db")
    base.update(over)
    return AppConfig(**base)


class TestFeatureStatus:
    def test_reflects_configured_features(self) -> None:
        cfg = _cfg(
            api_key=SecretStr("k"),
            google_speech_project_id="p",
            gemini_api_key=SecretStr("g"),
            auth_required=True,
        )
        status = health.feature_status(cfg)
        assert status.openrouter and status.speech and status.live
        assert status.auth_required and status.database_configured

    def test_absent_features_are_false(self) -> None:
        status = health.feature_status(_cfg())
        assert not status.openrouter and not status.speech and not status.live


class TestStartupValidation:
    def test_ok_with_database_and_soft_info_for_missing_optionals(self) -> None:
        ok, messages = health.startup_validation(_cfg())
        assert ok is True
        assert any("OpenRouter is not configured" in m for m in messages)
        assert any("Speech-to-Text not configured" in m for m in messages)
        assert any("Gemini Live not configured" in m for m in messages)

    def test_missing_database_is_a_hard_error(self) -> None:
        ok, messages = health.startup_validation(_cfg(database_url=""))
        assert ok is False
        assert any("ERROR" in m for m in messages)


class TestHealthCheck:
    def test_ok_when_core_configured_and_db_reachable(self) -> None:
        cfg = _cfg(api_key=SecretStr("k"))
        result = health.health_check(cfg, database_ok=True)
        assert result["status"] == "ok"
        assert result["checks"]["openrouter"] is True

    def test_degraded_without_openrouter(self) -> None:
        assert health.health_check(_cfg(), database_ok=True)["status"] == "degraded"

    def test_degraded_when_database_down(self) -> None:
        cfg = _cfg(api_key=SecretStr("k"))
        assert health.health_check(cfg, database_ok=False)["status"] == "degraded"
