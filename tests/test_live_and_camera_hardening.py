"""Phase 2E / Phase 3: Live hidden by default; camera coaching removed."""

from __future__ import annotations

from src.interview import studio_app


def test_live_disabled_by_default(monkeypatch):
    monkeypatch.delenv("INTERVIEW_LIVE_ENABLED", raising=False)
    assert studio_app._live_enabled() is False
    assert studio_app._answer_methods() == ["Type", "Record"]  # no Live


def test_live_enabled_via_flag(monkeypatch):
    monkeypatch.setenv("INTERVIEW_LIVE_ENABLED", "true")
    assert studio_app._live_enabled() is True
    assert "Live" in studio_app._answer_methods()


def test_live_flag_only_true_values(monkeypatch):
    for value in ("false", "0", "no", "", "off"):
        monkeypatch.setenv("INTERVIEW_LIVE_ENABLED", value)
        assert studio_app._live_enabled() is False


def test_camera_coaching_surfaces_removed():
    # The half-connected camera-coaching UI is gone (Phase 3 decision).
    for name in ("_render_camera_opt_in", "_render_visual_section",
                 "_render_visual_summary"):
        assert not hasattr(studio_app, name), f"{name} should be removed"
    # The module no longer imports the visual_coach helper.
    assert "visual_coach" not in dir(studio_app)
