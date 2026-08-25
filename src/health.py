"""Startup validation and a health check for production readiness.

These are pure, dependency-light helpers so they can back a ``/healthz`` probe,
a startup gate, or a CLI check without importing Streamlit. Nothing here ever
returns or logs a secret value — only booleans about whether a feature is
configured.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["FeatureStatus", "feature_status", "startup_validation", "health_check"]


@dataclass(frozen=True)
class FeatureStatus:
    """Which capabilities are configured (booleans only — never secret values)."""

    openrouter: bool
    speech: bool
    live: bool
    auth_required: bool
    database_configured: bool

    def as_dict(self) -> dict:
        return {
            "openrouter": self.openrouter,
            "speech": self.speech,
            "live": self.live,
            "auth_required": self.auth_required,
            "database_configured": self.database_configured,
        }


def feature_status(config) -> FeatureStatus:
    """Summarise configured features from an :class:`AppConfig`-like object."""
    return FeatureStatus(
        openrouter=bool(getattr(config, "is_configured", False)),
        speech=bool(getattr(config, "is_speech_configured", False)),
        live=bool(getattr(config, "is_live_configured", False)),
        auth_required=bool(getattr(config, "auth_required", False)),
        database_configured=bool(getattr(config, "database_url", "")),
    )


def startup_validation(config) -> tuple[bool, list[str]]:
    """Validate configuration at startup.

    Returns ``(ok, messages)``. ``ok`` is False only for hard errors that should
    stop production start; soft, expected gaps (e.g. optional voice not set) are
    returned as informational messages, not failures.
    """
    messages: list[str] = []
    ok = True

    if not getattr(config, "database_url", ""):
        ok = False
        messages.append("ERROR: no DATABASE_URL configured.")

    if getattr(config, "auth_required", False) and not getattr(
        config, "database_url", ""
    ):
        ok = False
        messages.append("ERROR: auth is required but no database is configured.")

    if not getattr(config, "is_configured", False):
        # Not fatal for local exploration, but the core feature needs it.
        messages.append(
            "INFO: OpenRouter is not configured; interviews cannot run until "
            "OPENROUTER_API_KEY is set."
        )
    if not getattr(config, "is_speech_configured", False):
        messages.append("INFO: Speech-to-Text not configured (Voice mode falls back).")
    if not getattr(config, "is_live_configured", False):
        messages.append("INFO: Gemini Live not configured (Live mode falls back).")

    return ok, messages


def health_check(config, *, database_ok: bool | None = None) -> dict:
    """A readiness snapshot suitable for a health endpoint.

    ``status`` is ``ok`` when the app can serve its core (OpenRouter) flow and
    the database is reachable; ``degraded`` when optional features are missing or
    a dependency is down. Never includes secret values.
    """
    features = feature_status(config)
    checks = features.as_dict()
    if database_ok is not None:
        checks["database_reachable"] = database_ok

    healthy = features.openrouter and (database_ok is not False)
    return {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
    }
