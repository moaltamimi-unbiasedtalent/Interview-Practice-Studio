"""Smoke test: the Career Intelligence module boots inside the unified shell."""

import pathlib

from streamlit.testing.v1 import AppTest

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def test_career_ui_imports() -> None:
    from src.career import ui  # noqa: F401


def test_shell_boots_and_exposes_career_routes() -> None:
    from src.ui import navigation as nav

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    options = [opt for radio in at.radio for opt in radio.options]
    # Default (candidate) view: the everyday routes are present...
    for section in ("Career Intelligence", "Knowledge Base"):
        assert nav.display_label(section) in options
    # ...and the Advanced diagnostics are hidden until reviewer mode.
    for section in ("RAG Inspector", "Evaluation"):
        assert nav.display_label(section) not in options


def test_reviewer_mode_reveals_advanced_routes(monkeypatch) -> None:
    from src.ui import navigation as nav

    monkeypatch.setenv("COPILOT_REVIEWER_MODE", "true")
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    options = [opt for radio in at.radio for opt in radio.options]
    for section in ("RAG Inspector", "Evaluation"):
        assert nav.display_label(section) in options


def test_career_route_renders_without_key() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["os_nav"] = "Career Intelligence"
    at.run()
    assert not at.exception
    # The Career Intelligence header renders even with no API key configured.
    assert any("Career Intelligence Copilot" in t.value for t in at.title)


def test_knowledge_base_route_renders() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["os_nav"] = "Knowledge Base"
    at.run()
    assert not at.exception
    assert any("Knowledge Base" in s.value for s in at.subheader)
