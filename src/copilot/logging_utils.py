"""Safe application logging for Career Intelligence Copilot.

Logging is metadata-only by policy. The rest of the app must NEVER log:
API keys, candidate CV/background content, pasted job descriptions, or raw user
queries. A future debug mode (``config.debug``) may add more detail, but it must
be designed to keep secrets and personal content out of the logs.
"""

from __future__ import annotations

import logging

__all__ = ["configure_logging", "get_logger"]

_CONFIGURED = False


def configure_logging(debug: bool = False) -> None:
    """Configure root logging once. INFO by default, DEBUG only when asked."""
    global _CONFIGURED
    if _CONFIGURED:
        logging.getLogger("career_copilot").setLevel(
            logging.DEBUG if debug else logging.INFO
        )
        return
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a namespaced logger (``career_copilot.<name>``).

    Callers must log only safe metadata — never keys, CVs, job descriptions or
    raw queries.
    """
    return logging.getLogger(f"career_copilot.{name}")
