"""Interview OS Coach — home / landing page."""

from __future__ import annotations

import streamlit as st

from src.ui import navigation as nav

__all__ = ["render_home"]


def _go(route: str) -> None:
    """Queue a navigation change consumed by app.py before the nav widget runs."""
    st.session_state["_pending_nav"] = route
    st.rerun()


def render_home() -> None:
    st.title(nav.APP_TITLE)
    st.markdown(f"**{nav.APP_TAGLINE}**")
    st.caption(
        "One platform, two modules: evidence-grounded career intelligence and "
        "realistic interview practice. Guidance and practice only — never a "
        "hiring decision."
    )

    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.subheader("Career Intelligence")
            st.write(
                "Understand a target role, identify skill gaps and build an "
                "evidence-grounded preparation strategy."
            )
            if st.button("Prepare for a role", key="home_career", use_container_width=True):
                _go(nav.CAREER)
    with right:
        with st.container(border=True):
            st.subheader("Interview Practice")
            st.write(
                "Practise realistic interviews, improve your answers and develop "
                "stronger delivery."
            )
            if st.button("Start practising", key="home_interview", use_container_width=True):
                _go(nav.INTERVIEW)

    st.divider()
    st.markdown("#### Platform workflow")
    st.markdown("**UNDERSTAND → PREPARE → PRACTISE → REVIEW → IMPROVE**")
    st.caption(
        "Career Intelligence covers Understand & Prepare; Interview Practice "
        "covers Practise, Review & Improve."
    )
