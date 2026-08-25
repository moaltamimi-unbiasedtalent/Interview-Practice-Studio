"""Tests for the live-interviewer component Python wrapper.

The frontend build (``frontend/dist``) is optional and gitignored, so it may or
may not be present. These tests assert the *contract* — availability reflects the
build state — rather than a fixed value, so they pass whether or not the
component has been built locally, and the app relies on this to fall back.
"""

import os

import pytest

from components import live_interviewer


def _dist_index() -> str:
    return os.path.join(live_interviewer.build_dir(), "index.html")


def test_availability_reflects_build_state() -> None:
    # is_available() is True exactly when the built frontend is present.
    assert live_interviewer.is_available() == os.path.isfile(_dist_index())


def test_build_dir_points_at_frontend_dist() -> None:
    path = live_interviewer.build_dir()
    assert path.endswith("frontend/dist")
    assert "live_interviewer" in path


def test_raises_only_when_unbuilt() -> None:
    # When the frontend is not built, calling it raises a clear error so callers
    # guard with is_available() and fall back. When it IS built, rendering needs
    # a Streamlit script context, so we skip the call here.
    if live_interviewer.is_available():
        pytest.skip("frontend is built; component render needs a Streamlit context")
    with pytest.raises(RuntimeError):
        live_interviewer.live_interviewer(session_config={"model": "x"})
