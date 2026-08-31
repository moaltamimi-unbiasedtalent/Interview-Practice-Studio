"""Interview OS Coach — the single Streamlit entry point.

    streamlit run app.py

One process, one URL. This shell owns ``st.set_page_config`` and the top-level
navigation, then delegates to the two product modules:

* Career Intelligence — ``src/career/ui.py`` (RAG chat, tools, KB, RAG Inspector,
  evaluation).
* Interview Practice — ``src/interview/studio_app.py`` (setup, strategy, dynamic
  questions, evaluation, Deep Dive, report, voice/live).

No business logic lives here. ``_build_configuration`` is re-exported for the
Interview Practice tests that import it from ``app``.
"""

from __future__ import annotations

import streamlit as st

from src.career import ui as career_ui
from src.interview.studio_app import _build_configuration  # re-exported for tests
from src.interview.studio_app import render_studio
from src.ui import navigation as nav
from src.ui.home import render_home

__all__ = ["main", "_build_configuration"]


def _resolve_active_page() -> str:
    """Resolve the single authoritative route from session state.

    There is ONE navigation state — ``nav.ACTIVE_PAGE_KEY``. Every navigation
    action (primary buttons, diagnostic buttons, queued ``_pending_nav`` from Home
    cards and the Career → Interview handoff) writes to it. No widget state is
    reconciled from the active page, so a user's click always survives the rerun.
    """
    ss = st.session_state

    # One-run migration from the legacy single key.
    if nav.ACTIVE_PAGE_KEY not in ss and "os_nav" in ss:
        ss[nav.ACTIVE_PAGE_KEY] = ss.pop("os_nav")

    # Queued navigation is applied before any widget is created.
    if "_pending_nav" in ss:
        target = ss.pop("_pending_nav")
        if target in nav.NAV_ITEMS:
            ss[nav.ACTIVE_PAGE_KEY] = target

    active = ss.get(nav.ACTIVE_PAGE_KEY, nav.HOME)
    if active not in nav.NAV_ITEMS:  # unknown/stale route → safe fallback
        active = nav.HOME
    ss[nav.ACTIVE_PAGE_KEY] = active
    return active


def main() -> None:
    st.set_page_config(page_title=nav.APP_TITLE, layout="wide")
    from src.ui.styles import inject_once

    inject_once()  # emit the small design-system style block for this run

    active = _resolve_active_page()

    from src.copilot.config import load_config

    reviewer_mode = load_config().reviewer_mode

    # --- Primary product navigation (top of sidebar) ---
    _render_primary_nav(active)

    # --- Route to the active page (renders its own sidebar content too) ---
    if active == nav.HOME:
        render_home()
    elif active == nav.INTERVIEW:
        render_studio()
    elif active in nav.CAREER_ROUTES:
        # Career module: shared config + its own sidebar, then the chosen page.
        career_ui.ensure_ready()
        career_ui.render_sidebar()
        if active == nav.CAREER:
            career_ui.render_career()
        elif active == nav.KNOWLEDGE_BASE:
            career_ui.render_knowledge_base()
        elif active == nav.RAG_INSPECTOR:
            career_ui.render_rag_inspector()
        elif active == nav.EVALUATION:
            career_ui.render_evaluation()

    # --- Secondary Review & diagnostics section (lower in the sidebar) ---
    _render_diagnostics_nav(active, reviewer_mode)


def _navigate(route: str) -> None:
    """Set the single active route and rerun."""
    st.session_state[nav.ACTIVE_PAGE_KEY] = route
    st.rerun()


def _render_primary_nav(active: str) -> None:
    """Primary product navigation as buttons over one authoritative route.

    The active route is a disabled primary-styled button (clear active state
    without relying on colour alone); the others are secondary buttons that set
    the active route and rerun.
    """
    st.sidebar.markdown(f"### {nav.APP_TITLE}")
    for route in nav.PRIMARY_NAV_ITEMS:
        is_active = active == route
        clicked = st.sidebar.button(
            nav.display_label(route),
            key=f"nav_{route}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            disabled=is_active,  # current page is not re-clickable → no needless rerun
        )
        if clicked:
            _navigate(route)
    st.sidebar.caption(nav.WORKFLOW)
    st.sidebar.divider()


def _render_diagnostics_nav(active: str, reviewer_mode: bool) -> None:
    """Render the always-available Review & diagnostics links below the main nav."""
    st.sidebar.divider()
    st.sidebar.caption("Review & diagnostics")
    for route in nav.DIAGNOSTIC_NAV_ITEMS:
        is_active = active == route
        clicked = st.sidebar.button(
            nav.DIAGNOSTIC_LABELS[route],
            key=f"diag_{route}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
            disabled=is_active,  # current diagnostic page reads as active
        )
        if clicked:
            _navigate(route)
    if nav.is_diagnostic(active):
        st.sidebar.caption(f"Viewing: {nav.DIAGNOSTIC_LABELS[active]}")
    if reviewer_mode:
        st.sidebar.caption("Reviewer mode")


if __name__ == "__main__":
    main()
