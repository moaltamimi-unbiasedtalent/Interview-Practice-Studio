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
    """Resolve the current page from queued navigation + the primary radio.

    Navigation can be set three ways: the primary radio (a primary route), the
    secondary diagnostic buttons (a diagnostic route), and queued ``_pending_nav``
    (Home cards, the Career → Interview handoff). The active page is tracked
    independently of the radio so a diagnostic page is never overwritten just
    because it is not one of the radio's options.
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

    ss.setdefault(nav.ACTIVE_PAGE_KEY, nav.HOME)
    ss.setdefault(nav.PRIMARY_NAV_KEY, nav.HOME)

    # When the active page is a primary route, the radio must reflect it (so a
    # queued/migrated primary page is not reset to Home by change-detection). A
    # diagnostic active page leaves the radio on its last primary selection.
    active = ss[nav.ACTIVE_PAGE_KEY]
    if active in nav.PRIMARY_NAV_ITEMS:
        ss[nav.PRIMARY_NAV_KEY] = active
        ss["_last_primary_radio"] = active
    ss.setdefault("_last_primary_radio", ss[nav.PRIMARY_NAV_KEY])
    return active


def main() -> None:
    st.set_page_config(page_title=nav.APP_TITLE, layout="wide")
    from src.ui.styles import inject_once

    inject_once()  # emit the small design-system style block for this run

    active = _resolve_active_page()
    ss = st.session_state

    from src.copilot.config import load_config

    reviewer_mode = load_config().reviewer_mode

    # --- Primary product navigation (top of sidebar) ---
    st.sidebar.markdown(f"### {nav.APP_TITLE}")
    radio_value = st.sidebar.radio(
        "Navigate",
        nav.PRIMARY_NAV_ITEMS,
        key=nav.PRIMARY_NAV_KEY,
        format_func=nav.display_label,
    )
    # A radio change wins; otherwise, while on a primary page, follow the radio.
    if radio_value != ss.get("_last_primary_radio"):
        active = radio_value
    elif active in nav.PRIMARY_NAV_ITEMS:
        active = radio_value
    ss["_last_primary_radio"] = radio_value
    ss[nav.ACTIVE_PAGE_KEY] = active

    st.sidebar.caption(nav.WORKFLOW)
    st.sidebar.divider()

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


def _render_diagnostics_nav(active: str, reviewer_mode: bool) -> None:
    """Render the always-available Review & diagnostics links below the main nav."""
    st.sidebar.divider()
    st.sidebar.caption("Review & diagnostics")
    for route in nav.DIAGNOSTIC_NAV_ITEMS:
        is_active = active == route
        if st.sidebar.button(
            nav.DIAGNOSTIC_LABELS[route],
            key=f"diag_{route}",
            use_container_width=True,
            disabled=is_active,  # current diagnostic page reads as active
        ):
            st.session_state[nav.ACTIVE_PAGE_KEY] = route
            st.rerun()
    if nav.is_diagnostic(active):
        st.sidebar.caption(f"Viewing: {nav.DIAGNOSTIC_LABELS[active]}")
    if reviewer_mode:
        st.sidebar.caption("Reviewer mode")


if __name__ == "__main__":
    main()
