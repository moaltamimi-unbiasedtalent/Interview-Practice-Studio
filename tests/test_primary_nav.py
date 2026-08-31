"""Primary sidebar navigation — real interaction tests (AppTest).

These click the actual sidebar controls (not just session state) so a navigation
regression like "selection snaps back to Home after a rerun" is caught. The
navigation model is button-based over one authoritative route (nav.ACTIVE_PAGE_KEY).
No live API calls.
"""

from __future__ import annotations

import pathlib

from streamlit.testing.v1 import AppTest

from src.ui import navigation as nav

APP_PATH = str(pathlib.Path(__file__).resolve().parent.parent / "app.py")


def _button(at, label):
    for b in at.button:
        if b.label == label:
            return b
    raise AssertionError(f"button '{label}' not found in {[b.label for b in at.button]}")


def _primary(at, route):
    return _button(at, nav.display_label(route))


def _diag(at, route):
    return _button(at, nav.DIAGNOSTIC_LABELS[route])


def _active(at):
    return at.session_state[nav.ACTIVE_PAGE_KEY]


def _go_primary(at, route):
    _primary(at, route).click()
    at.run()


# --- Regression: the exact reported bug (fails on the pre-fix radio model) ----


def test_regression_selection_survives_rerun() -> None:  # (section 13)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert _active(at) == nav.HOME
    _go_primary(at, nav.CAREER)
    assert not at.exception
    # Active route actually changed and stuck (did not snap back to Home)…
    assert _active(at) == nav.CAREER
    # …and the Career page content is what rendered.
    assert any("Career Intelligence Copilot" in t.value for t in at.title)


# --- Section 12 A–L ----------------------------------------------------------


def test_A_fresh_app_home_visible() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    assert not at.exception
    assert _active(at) == nav.HOME


def test_B_click_career_shows_career() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _go_primary(at, nav.CAREER)
    assert not at.exception
    assert _active(at) == nav.CAREER
    assert any("Career Intelligence Copilot" in t.value for t in at.title)


def test_C_career_to_interview() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _go_primary(at, nav.CAREER)
    _go_primary(at, nav.INTERVIEW)
    assert not at.exception
    assert _active(at) == nav.INTERVIEW


def test_D_interview_to_knowledge_base() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _go_primary(at, nav.INTERVIEW)
    _go_primary(at, nav.KNOWLEDGE_BASE)
    assert not at.exception
    assert _active(at) == nav.KNOWLEDGE_BASE
    assert any("Knowledge Base" in s.value for s in at.subheader)


def test_E_knowledge_base_to_home() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _go_primary(at, nav.KNOWLEDGE_BASE)
    _go_primary(at, nav.HOME)
    assert not at.exception
    assert _active(at) == nav.HOME


def test_F_full_journey_in_one_session() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    for route in (nav.CAREER, nav.HOME, nav.INTERVIEW, nav.KNOWLEDGE_BASE):
        _go_primary(at, route)
        assert not at.exception
        assert _active(at) == route


def test_G_career_to_rag_inspector_to_career() -> None:  # (section 11)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _go_primary(at, nav.CAREER)
    _diag(at, nav.RAG_INSPECTOR).click()
    at.run()
    assert _active(at) == nav.RAG_INSPECTOR
    _go_primary(at, nav.CAREER)
    assert not at.exception
    assert _active(at) == nav.CAREER


def test_H_career_to_evaluation_to_interview() -> None:  # (section 11)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _go_primary(at, nav.CAREER)
    _diag(at, nav.EVALUATION).click()
    at.run()
    assert _active(at) == nav.EVALUATION
    _go_primary(at, nav.INTERVIEW)
    assert not at.exception
    assert _active(at) == nav.INTERVIEW


def test_I_home_card_prepare_for_a_role() -> None:  # Home "Prepare for a role"
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _button(at, "Prepare for a role").click()
    at.run()
    assert not at.exception
    assert _active(at) == nav.CAREER


def test_J_home_card_start_practising() -> None:  # Home "Start practising"
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _button(at, "Start practising").click()
    at.run()
    assert not at.exception
    assert _active(at) == nav.INTERVIEW


def test_K_pending_nav_interview_practice() -> None:  # Career handoff
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["_pending_nav"] = nav.INTERVIEW
    at.run()
    assert not at.exception
    assert _active(at) == nav.INTERVIEW


def test_L_invalid_active_route_falls_back_to_home() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state[nav.ACTIVE_PAGE_KEY] = "Nonexistent Page"
    at.run()
    assert not at.exception
    assert _active(at) == nav.HOME


# --- Active-state clarity (section 8, 15) ------------------------------------


def test_active_primary_button_is_disabled() -> None:
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    # On Home, the Home button is the disabled/active one; others are clickable.
    assert _primary(at, nav.HOME).disabled is True
    assert _primary(at, nav.CAREER).disabled is False


def test_exactly_one_active_route_no_false_primary_on_diagnostic() -> None:  # (section 8)
    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.run()
    _diag(at, nav.RAG_INSPECTOR).click()
    at.run()
    # While on a diagnostic page, no primary button is marked active/disabled.
    for route in nav.PRIMARY_NAV_ITEMS:
        assert _primary(at, route).disabled is False
    # The diagnostic itself is the single active control.
    assert _diag(at, nav.RAG_INSPECTOR).disabled is True
