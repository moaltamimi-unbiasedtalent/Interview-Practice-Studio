"""Secondary (Review & diagnostics) navigation behaviour — AppTest driven.

Verifies diagnostics are reachable outside the primary radio, stay active across
reruns, coexist with primary navigation, and never break the queued
``_pending_nav`` handoff. No live API calls.
"""

from __future__ import annotations

import pathlib

import pytest
from streamlit.testing.v1 import AppTest

from src.ui import navigation as nav

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


@pytest.mark.parametrize("route", [
    nav.HOME, nav.CAREER, nav.INTERVIEW, nav.KNOWLEDGE_BASE,
    nav.RAG_INSPECTOR, nav.EVALUATION,
])
def test_all_six_pages_render_in_normal_mode(route) -> None:  # (section 15)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state[nav.ACTIVE_PAGE_KEY] = route
    at.run()
    assert not at.exception  # every page reachable without reviewer mode


def _diag_button(at, route):
    for b in at.button:
        if b.label == nav.DIAGNOSTIC_LABELS[route]:
            return b
    raise AssertionError(f"diagnostic button for {route} not found")


def _primary_button(at, route):
    for b in at.button:
        if b.label == nav.display_label(route):
            return b
    raise AssertionError(f"primary button for {route} not found")


def test_click_diagnostic_sets_active_page() -> None:  # (14 G)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _diag_button(at, nav.RAG_INSPECTOR).click()
    at.run()
    assert not at.exception
    assert at.session_state[nav.ACTIVE_PAGE_KEY] == nav.RAG_INSPECTOR


def test_diagnostic_stays_active_across_rerun() -> None:  # (14 H)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _diag_button(at, nav.EVALUATION).click()
    at.run()
    assert at.session_state[nav.ACTIVE_PAGE_KEY] == nav.EVALUATION
    at.run()  # a further rerun with no interaction
    assert at.session_state[nav.ACTIVE_PAGE_KEY] == nav.EVALUATION


def test_active_diagnostic_button_is_disabled() -> None:  # (14 H / section 8)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _diag_button(at, nav.RAG_INSPECTOR).click()
    at.run()
    assert _diag_button(at, nav.RAG_INSPECTOR).disabled is True


def test_primary_button_overrides_diagnostic() -> None:  # (14 I / 11)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _diag_button(at, nav.RAG_INSPECTOR).click()
    at.run()
    assert at.session_state[nav.ACTIVE_PAGE_KEY] == nav.RAG_INSPECTOR
    _primary_button(at, nav.INTERVIEW).click()
    at.run()
    assert not at.exception
    assert at.session_state[nav.ACTIVE_PAGE_KEY] == nav.INTERVIEW


def test_pending_nav_handoff_wins() -> None:  # (14 J)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["_pending_nav"] = nav.INTERVIEW  # e.g. Practise this role
    at.run()
    assert not at.exception
    assert at.session_state[nav.ACTIVE_PAGE_KEY] == nav.INTERVIEW


def test_home_card_navigation_still_works() -> None:  # (14 K)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["_pending_nav"] = nav.CAREER  # Home "Prepare for a role" card
    at.run()
    assert not at.exception
    assert at.session_state[nav.ACTIVE_PAGE_KEY] == nav.CAREER


def test_reviewer_mode_flag_does_not_gate_diagnostics(monkeypatch) -> None:  # (14 L)
    for value in ("true", "false"):
        monkeypatch.setenv("COPILOT_REVIEWER_MODE", value)
        at = AppTest.from_file(APP_PATH, default_timeout=30)
        at.run()
        assert not at.exception
        labels = [b.label for b in at.button]
        assert any("RAG Inspector" in label for label in labels)
        assert any("Evaluation" in label for label in labels)
