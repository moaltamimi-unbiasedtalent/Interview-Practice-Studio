"""Minimal, accessibility-preserving styling for Interview OS Coach.

Deliberately tiny: one small CSS block for badges/workflow chips. Everything else
uses native Streamlit components so keyboard operation, focus and screen-reader
labels are preserved. Colours meet contrast on both light and dark themes by
using Streamlit's theme variables where possible.
"""

from __future__ import annotations

import streamlit as st

__all__ = ["inject_once"]

_STYLE = """
<style>
.ios-badge {
  display: inline-block; padding: 0.1rem 0.5rem; margin: 0 0.25rem 0.25rem 0;
  border-radius: 0.5rem; font-size: 0.75rem; font-weight: 600; line-height: 1.4;
  border: 1px solid transparent;
}
.ios-badge.neutral { background:#e2e8f0; color:#1e293b; }
.ios-badge.info    { background:#dbeafe; color:#1e3a8a; }
.ios-badge.success { background:#dcfce7; color:#166534; }
.ios-badge.warn    { background:#fef3c7; color:#92400e; }
.ios-workflow { font-weight:600; letter-spacing:0.02em; }
</style>
"""


def inject_once() -> None:
    """Inject the small style block a single time per session run."""
    if not st.session_state.get("_ios_styles_injected"):
        st.markdown(_STYLE, unsafe_allow_html=True)
        st.session_state["_ios_styles_injected"] = True
