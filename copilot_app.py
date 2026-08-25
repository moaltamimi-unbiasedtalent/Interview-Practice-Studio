"""Career Intelligence Copilot — Streamlit shell (Phase 1 foundation).

Renders only. Pages are placeholders until later phases add RAG, tools and
evaluation. Booting this app must never require an API key and must never display
a secret. Run with:  streamlit run copilot_app.py
"""

from __future__ import annotations

import streamlit as st

from src.copilot import constants
from src.copilot.config import CopilotConfig, load_config
from src.copilot.logging_utils import configure_logging


def _render_header(config: CopilotConfig) -> None:
    st.title(constants.APP_NAME)
    st.markdown(f"**{constants.APP_TAGLINE}**")
    st.caption(
        "Guidance and preparation only — grounded in retrieved evidence, never "
        "an objective hiring decision."
    )
    if not config.is_configured:
        st.warning(
            "No OpenRouter API key is configured. Add `OPENROUTER_API_KEY` to "
            "`.streamlit/secrets.toml` or your environment to enable the model."
        )


def _render_status(config: CopilotConfig) -> None:
    # Status booleans only — never secret values.
    st.sidebar.divider()
    st.sidebar.markdown("### Status")
    st.sidebar.write(f"Model: `{config.default_model}`")
    st.sidebar.write(f"OpenRouter configured: {'✅' if config.is_configured else '❌'}")
    st.sidebar.caption(f"Vector store: `{config.chroma_persist_dir}` (built later)")


def _page_chat() -> None:
    st.subheader("Chat")
    st.info("The grounded career chat arrives in a later phase (RAG + tools).")
    st.chat_input("Ask a career question…", disabled=True)


def _page_knowledge_base() -> None:
    st.subheader("Knowledge Base")
    st.info(
        "Document ingestion, chunking and the vector index arrive in Phase 2–3. "
        "This page will show ingested sources and index stats."
    )


def _page_rag_inspector() -> None:
    st.subheader("RAG Inspector")
    st.info(
        "Query translation, retrieved chunks, citations and tool calls will be "
        "shown here once retrieval is built."
    )


def _page_evaluation() -> None:
    st.subheader("Evaluation")
    st.info("Retrieval and RAG evaluation dashboards arrive in a later phase.")


PAGES = {
    "Chat": _page_chat,
    "Knowledge Base": _page_knowledge_base,
    "RAG Inspector": _page_rag_inspector,
    "Evaluation": _page_evaluation,
}


def main() -> None:
    st.set_page_config(page_title=constants.APP_NAME, layout="wide")
    config = load_config()
    configure_logging(debug=config.debug)

    _render_header(config)
    page = st.sidebar.radio("Section", list(PAGES), key="copilot_page")
    _render_status(config)
    PAGES[page]()


if __name__ == "__main__":
    main()
