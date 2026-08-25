"""Shared design-system helpers for a consistent Interview OS Coach experience.

Thin wrappers over native Streamlit components (plus one tiny badge style) so the
two modules look like one product. Native components keep keyboard operation,
focus order and screen-reader labels intact.
"""

from __future__ import annotations

from contextlib import contextmanager
from html import escape

import streamlit as st

__all__ = [
    "page_header",
    "section_header",
    "card",
    "badge",
    "badges",
    "alert",
    "loading",
    "source_card",
    "action_button",
    "empty_state",
]

_ALERT_FUNCS = {"info": st.info, "success": st.success, "warn": st.warning, "error": st.error}


def page_header(title: str, subtitle: str | None = None, caption: str | None = None) -> None:
    """A consistent page title (H1) + optional subtitle and caption."""
    st.title(title)
    if subtitle:
        st.markdown(f"**{subtitle}**")
    if caption:
        st.caption(caption)


def section_header(title: str, help: str | None = None) -> None:
    """A consistent section title (H3)."""
    st.subheader(title, help=help)


@contextmanager
def card(border: bool = True):
    """A bordered content container. Use as a context manager."""
    with st.container(border=border):
        yield


def badge(text: str, tone: str = "neutral") -> None:
    """A small inline badge (neutral | info | success | warn)."""
    tone = tone if tone in ("neutral", "info", "success", "warn") else "neutral"
    st.markdown(f'<span class="ios-badge {tone}">{escape(text)}</span>', unsafe_allow_html=True)


def badges(items: list[str], tone: str = "neutral") -> None:
    """Render a row of badges from a list of labels."""
    if not items:
        return
    spans = "".join(
        f'<span class="ios-badge {tone}">{escape(str(i))}</span>' for i in items
    )
    st.markdown(spans, unsafe_allow_html=True)


def alert(message: str, tone: str = "info") -> None:
    """A themed alert (info | success | warn | error)."""
    _ALERT_FUNCS.get(tone, st.info)(message)


@contextmanager
def loading(message: str = "Working…"):
    """A consistent loading/progress state. Use as a context manager."""
    with st.status(message, expanded=False) as status:
        yield status


def source_card(title: str | None, source: str | None = None, page: int | None = None,
                snippet: str | None = None) -> None:
    """A compact citation/source card (provenance, not scoring)."""
    label = title or source or "Source"
    locator = f" · page {page}" if page is not None else ""
    with st.container(border=True):
        st.markdown(f"**{label}**{locator}")
        if source and source != label:
            st.caption(source)
        if snippet:
            st.caption(snippet[:300] + ("…" if len(snippet) > 300 else ""))


def action_button(label: str, key: str, *, primary: bool = False,
                  disabled: bool = False, use_container_width: bool = True) -> bool:
    """A consistent action button."""
    return st.button(
        label,
        key=key,
        type="primary" if primary else "secondary",
        disabled=disabled,
        use_container_width=use_container_width,
    )


def empty_state(title: str, body: str, hint: str | None = None) -> None:
    """A friendly empty state with an optional next-step hint."""
    with st.container(border=True):
        st.markdown(f"#### {title}")
        st.write(body)
        if hint:
            st.caption(hint)
