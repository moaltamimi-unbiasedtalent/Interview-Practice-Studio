"""Interview OS Coach — home / landing page."""

from __future__ import annotations

import streamlit as st

from src.ui import navigation as nav
from src.ui import shared

__all__ = ["render_home"]


def _go(route: str) -> None:
    """Queue a navigation change consumed by app.py before the nav widget runs."""
    st.session_state["_pending_nav"] = route
    st.rerun()


def render_home() -> None:
    shared.page_header(
        nav.APP_TITLE,
        subtitle=nav.APP_TAGLINE,
        caption=(
            "One platform, two modules: evidence-grounded career intelligence and "
            "realistic interview practice. Guidance and practice only — never a "
            "hiring decision."
        ),
    )

    left, right = st.columns(2)
    with left:
        with shared.card():
            shared.section_header("Prepare · Career Intelligence")
            st.write(
                "Understand a target role, identify skill gaps and build an "
                "evidence-grounded preparation strategy."
            )
            if shared.action_button("Prepare for a role", key="home_career", primary=True):
                _go(nav.CAREER)
    with right:
        with shared.card():
            shared.section_header("Practise · Interview Practice")
            st.write(
                "Practise realistic interviews, improve your answers and develop "
                "stronger delivery."
            )
            if shared.action_button("Start practising", key="home_interview", primary=True):
                _go(nav.INTERVIEW)

    st.info(
        "**Recommended journey: Prepare → Practise.** Start in Career Intelligence "
        "to understand the role and build an evidence-grounded plan, then hand it "
        "straight to Interview Practice with **Practise this role**.",
        icon="🧭",
    )

    st.divider()
    shared.section_header("How it works")
    st.markdown(f'<span class="ios-workflow">{nav.WORKFLOW}</span>', unsafe_allow_html=True)
    shared.badges(nav.WORKFLOW_STEPS, tone="info")
    st.caption(
        "Career Intelligence covers Understand & Prepare; Interview Practice "
        "covers Practise, Review & Improve."
    )
