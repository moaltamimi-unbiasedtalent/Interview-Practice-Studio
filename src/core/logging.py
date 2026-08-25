"""One safe logging policy for the whole platform.

Never log candidate backgrounds, job descriptions, RAG chunks, model response
content, transcripts or credentials. Log **safe metadata only** — sizes, counts,
model ids, durations, verdicts. :func:`safe_extra` redacts sensitive fields so a
careless log call cannot leak content.
"""

from __future__ import annotations

import logging

__all__ = ["SENSITIVE_KEYS", "safe_extra", "get_logger", "configure_logging"]

# Field names whose values must never be logged verbatim.
SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "secret",
        "password",
        "token",
        "credential",
        "credentials",
        "authorization",
        "candidate_background",
        "background",
        "job_description",
        "jd",
        "transcript",
        "chunk",
        "chunks",
        "content",
        "response",
        "answer",
        "prompt",
        "system_prompt",
        "query",
        "text",
    }
)

_REDACTED = "[REDACTED]"


def safe_extra(**fields) -> dict:
    """Return a log-safe ``extra`` mapping with sensitive values redacted."""
    return {
        key: (_REDACTED if key.lower() in SENSITIVE_KEYS else value)
        for key, value in fields.items()
    }


def get_logger(name: str = "interview_os") -> logging.Logger:
    """Return the platform logger (child loggers by dotted name)."""
    return logging.getLogger(name)


def configure_logging(debug: bool = False) -> None:
    """Configure root logging once; INFO by default, DEBUG when requested."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
