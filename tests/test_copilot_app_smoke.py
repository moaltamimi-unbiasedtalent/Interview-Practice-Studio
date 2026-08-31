"""Smoke test: the Career Intelligence module boots inside the unified shell."""

import pathlib

from streamlit.testing.v1 import AppTest

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def test_career_ui_imports() -> None:
    from src.career import ui  # noqa: F401


def test_shell_boots_with_primary_radio_only() -> None:
    from src.ui import navigation as nav

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    options = [opt for radio in at.radio for opt in radio.options]
    # Primary product routes are in the top radio…
    for section in nav.PRIMARY_NAV_ITEMS:
        assert nav.display_label(section) in options
    # …and diagnostics are NOT radio options (they are secondary buttons).
    for section in nav.DIAGNOSTIC_NAV_ITEMS:
        assert nav.display_label(section) not in options


def test_diagnostics_are_buttons_in_normal_mode() -> None:
    # RAG Inspector + Evaluation must be reachable WITHOUT reviewer mode.
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert any("RAG Inspector" in label for label in labels)
    assert any("Evaluation" in label for label in labels)


def test_reviewer_mode_still_shows_diagnostics(monkeypatch) -> None:
    monkeypatch.setenv("COPILOT_REVIEWER_MODE", "true")
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    labels = [b.label for b in at.button]
    assert any("RAG Inspector" in label for label in labels)


def test_career_route_renders_without_key() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["os_active_page"] = "Career Intelligence"
    at.run()
    assert not at.exception
    # The Career Intelligence header renders even with no API key configured.
    assert any("Career Intelligence Copilot" in t.value for t in at.title)


def test_legacy_os_nav_key_is_migrated() -> None:
    # Backward compatibility: the old single key still routes correctly.
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["os_nav"] = "Knowledge Base"
    at.run()
    assert not at.exception
    assert any("Knowledge Base" in s.value for s in at.subheader)


def test_knowledge_base_route_renders() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["os_active_page"] = "Knowledge Base"
    at.run()
    assert not at.exception
    assert any("Knowledge Base" in s.value for s in at.subheader)
