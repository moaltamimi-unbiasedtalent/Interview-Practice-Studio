"""Package-based Streamlit component for the live AI interviewer.

The frontend (``frontend/``, TypeScript) owns all high-frequency audio and
WebSocket work — microphone capture, 16 kHz resampling, ~30 ms chunking, the
Gemini Live connection, playback, interruption, transcripts and bounded
reconnect — kept isolated from the Python interview domain logic.

This module is a thin, safe wrapper:

* it declares the bidirectional component only when the frontend has been built;
* :func:`is_available` lets the app fall back cleanly when it has not;
* it forwards only the *non-secret* session config (ephemeral token, model,
  audio parameters) to the browser and returns the component's event payload
  (state, transcript) back to Python.

The permanent Gemini key is never passed here — only the ephemeral token minted
by :class:`src.live_interview.GeminiLiveTokenService`.
"""

from __future__ import annotations

import os
from typing import Any

_BUILD_DIR = os.path.join(os.path.dirname(__file__), "frontend", "dist")

__all__ = ["is_available", "live_interviewer", "build_dir"]


def build_dir() -> str:
    """Absolute path to the expected frontend build directory."""
    return _BUILD_DIR


def is_available() -> bool:
    """True only when the frontend has been built (``frontend/dist`` exists)."""
    return os.path.isdir(_BUILD_DIR) and os.path.isfile(
        os.path.join(_BUILD_DIR, "index.html")
    )


def _component_func():
    # Imported lazily so importing this package never requires Streamlit.
    import streamlit.components.v1 as components

    return components.declare_component("live_interviewer", path=_BUILD_DIR)


def live_interviewer(
    *, session_config: dict[str, Any], key: str | None = None, default: Any = None
) -> Any:
    """Render the live-interviewer component and return its latest event.

    ``session_config`` is the non-secret payload from
    :meth:`LiveInterviewService.start_session` (ephemeral token, model, sample
    rates, chunk size, reconnect bound). Raises ``RuntimeError`` if the frontend
    build is missing — callers should check :func:`is_available` first and fall
    back to recorded voice or text.
    """
    if not is_available():
        raise RuntimeError(
            "The live_interviewer frontend build is missing. Build it with "
            "`cd components/live_interviewer/frontend && npm install && npm run "
            "build`, or use Voice/Text practice."
        )
    return _component_func()(
        session_config=session_config, key=key, default=default
    )
