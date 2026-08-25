"""Single source of truth for reading secrets and settings.

Precedence is **Streamlit secrets → environment variables**, with no default
real keys. Both the Career and Interview config modules delegate their raw
reads here, so the precedence, the tolerant Streamlit access, and the SecretStr
masking live in exactly one place.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import SecretStr

__all__ = [
    "load_dotenv_once",
    "read_streamlit",
    "read_env",
    "read_setting",
    "read_bool",
    "read_float",
    "read_secret",
]


def load_dotenv_once() -> None:
    """Load a local ``.env`` for development, never overriding real env vars."""
    load_dotenv(override=False)


def read_streamlit(name: str) -> str | None:
    """Read a value from Streamlit secrets, tolerating a no-secrets environment.

    Streamlit raises when no secrets file exists at all — expected in local dev
    and tests — so that is treated as "not configured", never a failure.
    """
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def read_env(name: str) -> str | None:
    """Read a value from the environment (local-development fallback)."""
    value = os.environ.get(name)
    return value.strip() if value and value.strip() else None


def read_setting(name: str) -> str | None:
    """Streamlit secrets take precedence over the environment."""
    return read_streamlit(name) or read_env(name)


def read_bool(name: str, default: bool = False) -> bool:
    raw = read_setting(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def read_float(name: str, default: float) -> float:
    raw = read_setting(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def read_secret(name: str) -> SecretStr | None:
    """Read a credential as ``SecretStr`` (masked if printed/logged), or None."""
    raw = read_setting(name)
    return SecretStr(raw) if raw else None
