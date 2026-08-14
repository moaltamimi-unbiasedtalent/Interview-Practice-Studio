"""Tests for the live-interviewer component Python wrapper.

The frontend is not built in CI, so the wrapper must degrade gracefully rather
than crash — the app relies on this to fall back to voice/text.
"""

import pytest

from components import live_interviewer


def test_component_unavailable_without_build() -> None:
    # No frontend/dist in CI → unavailable, so the app shows the fallback.
    assert live_interviewer.is_available() is False


def test_build_dir_points_at_frontend_dist() -> None:
    path = live_interviewer.build_dir()
    assert path.endswith("frontend/dist")
    assert "live_interviewer" in path


def test_live_interviewer_raises_when_unbuilt() -> None:
    # Calling it without a build raises a clear error (callers guard with
    # is_available and fall back instead).
    with pytest.raises(RuntimeError):
        live_interviewer.live_interviewer(session_config={"model": "x"})
