"""Smoke test: the Copilot Streamlit shell imports and boots without a key."""

import pathlib

from streamlit.testing.v1 import AppTest

APP_PATH = str(
    pathlib.Path(__file__).resolve().parent.parent / "copilot_app.py"
)


def test_copilot_app_imports() -> None:
    import copilot_app  # noqa: F401


def test_copilot_app_boots_without_exception() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert any("Career Intelligence Copilot" in t.value for t in at.title)


def test_copilot_sections_present() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    options = [opt for radio in at.radio for opt in radio.options]
    for section in ("Chat", "Knowledge Base", "RAG Inspector", "Evaluation"):
        assert section in options
