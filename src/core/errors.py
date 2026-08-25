"""Coherent, safe exception hierarchy for the platform.

The UI shows ``user_message`` (always safe); the underlying types stay specific
so they remain testable and catchable. Domain modules may subclass these where
useful, but keep their own specific exceptions too.
"""

from __future__ import annotations

__all__ = ["InterviewOSError", "ConfigError", "SafeError"]


class InterviewOSError(Exception):
    """Base class for platform errors."""


class ConfigError(InterviewOSError):
    """Raised when configuration is missing or invalid."""


class SafeError(InterviewOSError):
    """An error carrying a user-safe message, hiding any sensitive detail."""

    def __init__(self, user_message: str, *, detail: str | None = None) -> None:
        super().__init__(user_message)
        self.user_message = user_message
        # ``detail`` is for logs/tests only — never rendered to end users.
        self.detail = detail
