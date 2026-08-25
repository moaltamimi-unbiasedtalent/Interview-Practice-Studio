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


def main() -> None:
    st.set_page_config(page_title=nav.APP_TITLE, layout="wide")

    # Home cards queue a route change; apply it before the nav widget is created
    # (mutating a widget key after instantiation is not allowed).
    if "_pending_nav" in st.session_state:
        st.session_state["os_nav"] = st.session_state.pop("_pending_nav")

    page = st.sidebar.radio(nav.APP_TITLE, nav.NAV_ITEMS, key="os_nav")
    st.sidebar.divider()

    if page == nav.HOME:
        render_home()
    elif page == nav.INTERVIEW:
        render_studio()
    elif page in nav.CAREER_ROUTES:
        # Career module: shared config + its own sidebar, then the chosen page.
        career_ui.ensure_ready()
        career_ui.render_sidebar()
        if page == nav.CAREER:
            career_ui.render_career()
        elif page == nav.KNOWLEDGE_BASE:
            career_ui.render_knowledge_base()
        elif page == nav.RAG_INSPECTOR:
            career_ui.render_rag_inspector()
        elif page == nav.EVALUATION:
            career_ui.render_evaluation()


if __name__ == "__main__":
    main()
