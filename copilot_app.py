"""Career Intelligence Copilot — Streamlit shell.

Phase 3 makes the Chat page a working evidence-grounded chatbot (vector RAG) and
the RAG Inspector a transparency view over each query. Booting this app must
never require an API key and must never display a secret or the system prompt.
Run with:  streamlit run copilot_app.py
"""

from __future__ import annotations

import streamlit as st

from src.copilot import constants
from src.copilot.config import CopilotConfig, load_config
from src.copilot.logging_utils import configure_logging
from src.copilot.rag import build_context
from src.copilot.rag.chain import RagChain, RagChainError
from src.copilot.rag.translation import QueryTranslator
from src.copilot.retrieval.vector import VectorRetriever


# --- Shared resources --------------------------------------------------------


@st.cache_resource(show_spinner=False)
def _get_store(_config: CopilotConfig):
    """Build the vector store once per session (secrets not part of cache key)."""
    from src.copilot.vectorstore import build_vector_store

    return build_vector_store(_config)


def _config() -> CopilotConfig:
    return st.session_state["copilot_config"]


# --- Header / status ---------------------------------------------------------


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
    try:
        count = _get_store(config).count()
        st.sidebar.write(f"Indexed chunks: {count}")
    except Exception:  # pragma: no cover - defensive UI guard
        st.sidebar.write("Indexed chunks: unavailable")
    st.sidebar.caption(f"Vector store: `{config.chroma_persist_dir}`")


# --- Chat --------------------------------------------------------------------


def _render_sources(results, citations) -> None:
    if citations:
        st.markdown("**Sources**")
        for citation in citations:
            st.markdown(citation.label)
    if results:
        with st.expander(f"Retrieved passages ({len(results)})"):
            for index, result in enumerate(results, start=1):
                title = result.title or "Untitled source"
                page = f" · page {result.page}" if result.page is not None else ""
                st.markdown(f"**[{index}] {title}{page}** — score {result.score:.3f}")
                st.caption(result.text[:600] + ("…" if len(result.text) > 600 else ""))


def _page_chat() -> None:
    st.subheader("Chat")
    config = _config()

    if not config.is_configured:
        st.info(
            "Add an OpenRouter API key to enable grounded chat. Retrieval still "
            "works, but answering needs the model."
        )
        st.chat_input("Ask a career question…", disabled=True)
        return

    store = _get_store(config)
    if store.count() == 0:
        st.info(
            "The knowledge base is empty. Add sources to `data/raw/`, then run "
            "`python scripts/ingest.py` and `python scripts/build_index.py`."
        )
        st.chat_input("Ask a career question…", disabled=True)
        return

    st.session_state.setdefault("chat_history", [])
    for message in st.session_state["chat_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                _render_sources(message.get("results", []), message.get("citations", []))

    prompt = st.chat_input("Ask a career question…")
    if not prompt:
        return

    prompt = prompt.strip()[: constants.MAX_QUERY_CHARS]
    st.session_state["chat_history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    retriever = VectorRetriever(store)
    translator = QueryTranslator(config=config)
    chain = RagChain(retriever, config=config, translator=translator)

    with st.chat_message("assistant"):
        with st.status("Understanding question…", expanded=False) as status:
            translated = chain.translate(prompt)
            status.update(label="Searching knowledge base…")
            results = chain.retrieve_translated(translated)
            bundle = build_context(results)
            status.update(label="Preparing answer…")
            try:
                response = chain.answer(prompt, translated=translated, results=results)
            except RagChainError as exc:
                status.update(label="Failed", state="error")
                st.error(str(exc))
                return
            status.update(label="Done", state="complete")

        st.markdown(response.answer)
        _render_sources(results, response.citations)

    # Persist for re-render and for the RAG Inspector (no secrets, no prompt).
    st.session_state["chat_history"].append(
        {
            "role": "assistant",
            "content": response.answer,
            "citations": response.citations,
            "results": results,
        }
    )
    st.session_state["last_inspection"] = {
        "query": prompt,
        "translated": translated,
        "results": results,
        "context_text": bundle.context_text,
        "usage": response.usage,
    }


# --- Knowledge Base ----------------------------------------------------------


def _page_knowledge_base() -> None:
    st.subheader("Knowledge Base")
    from src.copilot.ingestion import indexer

    manifest = indexer.load_manifest()
    if not manifest:
        st.info(
            "No knowledge base ingested yet. Add sources to `data/raw/` (see its "
            "README) and run `python scripts/ingest.py`."
        )
        return

    columns = st.columns(3)
    columns[0].metric("Documents", manifest.get("documents", 0))
    columns[1].metric("Chunks", manifest.get("chunks", 0))
    columns[2].metric("Document types", len(manifest.get("by_type", {})))

    by_type = manifest.get("by_type", {})
    if by_type:
        st.markdown("**By document type**")
        st.write({k: v for k, v in by_type.items()})

    per_doc = manifest.get("per_document", [])
    if per_doc:
        st.markdown("**Ingested documents**")
        st.dataframe(
            [
                {
                    "File": d.get("filename"),
                    "Type": d.get("document_type"),
                    "Title": d.get("title"),
                    "Chunks": d.get("chunks"),
                }
                for d in per_doc
            ],
            use_container_width=True,
        )
    errors = manifest.get("errors", [])
    if errors:
        st.warning(f"{len(errors)} document(s) could not be ingested.")
    st.caption(
        "Run `python scripts/build_index.py` after ingesting to embed chunks into "
        "the vector store."
    )


# --- RAG Inspector -----------------------------------------------------------


def _page_rag_inspector() -> None:
    st.subheader("RAG Inspector")
    st.caption(
        "Transparency view for the last query. System prompts and secrets are "
        "never shown."
    )
    inspection = st.session_state.get("last_inspection")
    if not inspection:
        st.info("Ask a question on the Chat page to inspect its retrieval here.")
        return

    translated = inspection.get("translated")
    st.markdown("**Original query**")
    st.code(inspection["query"], language="text")

    if translated is not None:
        st.markdown("**Query translation**")
        columns = st.columns(2)
        columns[0].write(f"Intent: `{translated.intent}`")
        columns[1].write(f"Retrieval required: {'✅' if translated.retrieval_required else '❌'}")
        st.write("Rewritten query:")
        st.code(translated.rewritten_query, language="text")
        if translated.alternate_queries:
            st.write("Alternative queries:")
            for alt in translated.alternate_queries:
                st.markdown(f"- {alt}")
        st.write(f"Metadata filters: `{translated.metadata_filters or '{}'}`")
        if translated.explanation:
            st.caption(f"Why: {translated.explanation}")
        if translated.strategy != "llm":
            st.caption(f"(translation strategy: {translated.strategy})")

    results = inspection["results"]
    st.markdown(f"**Retrieved chunks ({len(results)})**")
    if results:
        st.dataframe(
            [
                {
                    "#": i,
                    "Score": round(r.score, 4),
                    "Title": r.title,
                    "Page": r.page,
                    "Type": r.metadata.get("document_type"),
                    "Chunk id": r.chunk.chunk_id,
                }
                for i, r in enumerate(results, start=1)
            ],
            use_container_width=True,
        )
        for i, r in enumerate(results, start=1):
            with st.expander(f"[{i}] {r.title or 'Untitled'} — full metadata & text"):
                st.json(r.metadata)
                st.text(r.text)
    else:
        st.warning("No chunks were retrieved for this query.")

    st.markdown("**Context sent to the model**")
    st.caption("Exactly the numbered passages the model saw (no system prompt).")
    st.code(inspection["context_text"] or "(empty)", language="text")

    usage = inspection.get("usage")
    if usage is not None:
        st.markdown("**Token usage**")
        st.write(
            {
                "prompt_tokens": usage.prompt_tokens,
                "completion_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
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
    st.session_state["copilot_config"] = config
    configure_logging(debug=config.debug)

    _render_header(config)
    page = st.sidebar.radio("Section", list(PAGES), key="copilot_page")
    _render_status(config)
    PAGES[page]()


if __name__ == "__main__":
    main()
