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
from src.copilot.retrieval import build_retriever
from src.copilot.retrieval.hybrid import HybridRetriever


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


def _results_table(results) -> None:
    """Compact table of retrieval results (used by the RAG Inspector)."""
    if not results:
        st.caption("— none —")
        return
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
        hide_index=True,
    )


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

    mode = st.session_state.get("retrieval_mode", config.retrieval_mode)
    retriever = build_retriever(config, mode=mode, store=store)
    translator = QueryTranslator(config=config)
    chain = RagChain(retriever, config=config, translator=translator)

    hybrid_detail = None
    with st.chat_message("assistant"):
        with st.status("Understanding question…", expanded=False) as status:
            translated = chain.translate(prompt)
            status.update(label="Searching knowledge base…")
            results = chain.retrieve_translated(translated)
            # For the inspector, capture the per-channel detail of the rewritten query.
            if isinstance(retriever, HybridRetriever) and translated.retrieval_required:
                hybrid_detail = retriever.search(
                    translated.rewritten_query,
                    top_k=chain.top_k,
                    filters=translated.metadata_filters or None,
                )
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
        "mode": mode,
        "translated": translated,
        "results": results,
        "hybrid": hybrid_detail,
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
    if inspection.get("mode"):
        st.caption(f"Retrieval mode: `{inspection['mode']}`")

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

    hybrid = inspection.get("hybrid")
    if hybrid is not None:
        st.markdown("**Hybrid channels** (rewritten query)")
        st.caption(
            "Vector (semantic) and BM25 (lexical) hits, then their reciprocal-rank "
            "fusion. Scores are per-channel and not directly comparable."
        )
        cols = st.columns(2)
        with cols[0]:
            st.write(f"Vector hits ({len(hybrid.vector)})")
            _results_table(hybrid.vector)
        with cols[1]:
            st.write(f"Keyword/BM25 hits ({len(hybrid.keyword)})")
            _results_table(hybrid.keyword)
        st.write(f"Fused ranking ({len(hybrid.fused)})")
        _results_table(hybrid.fused)

    results = inspection["results"]
    st.markdown(f"**Final result set ({len(results)})**")
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


def _render_tools_used() -> None:
    executions = st.session_state.get("tool_executions", [])
    if not executions:
        return
    with st.expander(f"🛠 Tools used ({len(executions)})", expanded=False):
        for ex in executions:
            mark = "✓" if ex.status == "ok" else "✗"
            st.markdown(f"{mark} **{ex.tool_name}** — `{ex.status}` ({ex.duration_seconds:.3f}s)")
            if ex.safe_argument_summary:
                st.caption(f"args: {ex.safe_argument_summary}")
            if ex.safe_result_summary:
                st.caption(f"result: {ex.safe_result_summary}")
            if ex.error:
                st.caption(f"error: {ex.error}")


def _run_tool(invoker, name: str, args: dict):
    """Invoke a tool, record its safe execution, and surface errors in the UI."""
    result = invoker.invoke(name, args)
    st.session_state.setdefault("tool_executions", []).append(result.execution)
    if not result.ok:
        st.error(f"{name}: {result.execution.status} — {result.execution.error}")
        return None
    return result.result


def _page_tools() -> None:
    st.subheader("Career Tools")
    st.caption(
        "Domain tools for interview prep. Deterministic tools compute their own "
        "statistics in Python; the LLM tools need an API key. This is coaching, "
        "not a hiring decision."
    )
    config = _config()

    from src.copilot.tools import ToolInvoker, build_tool_registry

    invoker = ToolInvoker(build_tool_registry(config=config))
    ss = st.session_state

    # 1) Job Description Analyzer -------------------------------------------
    st.markdown("### 1. Job Description Analyzer")
    jd = st.text_area("Paste a job description", height=160, key="tool_jd")
    if st.button("Analyze job description", disabled=not config.is_configured):
        if jd.strip():
            with st.spinner("Analyzing…"):
                ss["role_requirements"] = _run_tool(
                    invoker, constants.TOOL_JOB_ANALYZER, {"job_description": jd}
                )
    role_req = ss.get("role_requirements")
    if role_req is not None:
        st.write(f"**Role:** {role_req.role_title or 'n/a'} · **Seniority:** {role_req.seniority or 'n/a'}")
        cols = st.columns(2)
        cols[0].write("Required skills"); cols[0].write(role_req.required_skills or "—")
        cols[1].write("Technologies"); cols[1].write(role_req.technologies or "—")
        if role_req.interpretation_notes:
            st.caption("Interpretation (not explicit in the JD): " + "; ".join(role_req.interpretation_notes))

    # 2) Candidate Gap Analyzer --------------------------------------------
    st.markdown("### 2. Candidate Gap Analyzer")
    background = st.text_area("Candidate background / CV summary", height=140, key="tool_bg")
    if st.button("Analyze gaps", disabled=role_req is None):
        if background.strip():
            ss["gap_result"] = _run_tool(
                invoker,
                constants.TOOL_GAP_ANALYZER,
                {"candidate_background": background, "role_requirements": role_req.model_dump()},
            )
    gap = ss.get("gap_result")
    if gap is not None:
        s = gap.stats
        cols = st.columns(3)
        cols[0].metric("Match", f"{s.match_percentage}%")
        cols[1].metric("Weighted", f"{s.weighted_match_percentage}%")
        cols[2].metric("Requirements", s.total_requirements)
        st.write(f"Matched: {gap.matched or '—'}")
        st.write(f"Partial: {gap.partially_matched or '—'}")
        st.write(f"Missing: {gap.missing or '—'}")
        st.caption("All percentages are computed in Python from explicit criteria.")

    # 3) Preparation Plan Calculator ---------------------------------------
    st.markdown("### 3. Preparation Plan Calculator")
    cols = st.columns(2)
    days = cols[0].number_input("Days until interview", min_value=1, max_value=365, value=14)
    hpw = cols[1].number_input("Hours per week", min_value=1.0, max_value=80.0, value=6.0)
    if st.button("Build preparation plan", disabled=gap is None or not gap.priority_gaps):
        ss["prep_plan"] = _run_tool(
            invoker,
            constants.TOOL_PREP_PLANNER,
            {
                "priority_gaps": [g.model_dump() for g in gap.priority_gaps],
                "days_until_interview": int(days),
                "hours_per_week": float(hpw),
            },
        )
    plan = ss.get("prep_plan")
    if plan is not None:
        st.write(f"**Total available hours:** {plan.total_available_hours}")
        st.dataframe(
            [
                {"Gap": a.requirement, "Severity": a.severity, "Hours": a.allocated_hours, "Share %": a.share_percentage}
                for a in plan.allocations
            ],
            use_container_width=True,
            hide_index=True,
        )
        for wk in plan.weekly_structure:
            st.caption(f"Week {wk.week}: {wk.hours}h — focus: {', '.join(wk.focus) or '—'}")

    # 4) Interview Question Generator --------------------------------------
    st.markdown("### 4. Interview Question Generator")
    default_role = role_req.role_title if role_req and role_req.role_title else ""
    role_name = st.text_input("Role", value=default_role, key="tool_role")
    focus = st.multiselect("Focus categories", list(constants.QUESTION_CATEGORIES))
    if st.button("Generate questions", disabled=not config.is_configured or not role_name.strip()):
        reqs = (role_req.required_skills + role_req.technologies) if role_req else []
        with st.spinner("Generating…"):
            ss["question_set"] = _run_tool(
                invoker,
                constants.TOOL_QUESTION_GENERATOR,
                {"role": role_name, "requirements": reqs, "focus": focus},
            )
    qset = ss.get("question_set")
    if qset is not None:
        for category in qset.categories:
            st.markdown(f"**{category.name}**")
            for q in category.questions:
                st.markdown(f"- {q}")

    _render_tools_used()


def _page_evaluation() -> None:
    st.subheader("Evaluation")
    config = _config()
    st.markdown("**Retrieval comparison (vector / keyword / hybrid)**")
    st.caption(
        "Lexical proxy metrics over probes in `data/eval/retrieval_probes.json`. "
        "These characterise exact-term behaviour and do NOT prove one mode is "
        "better overall — that needs labelled relevance judgements."
    )

    store = _get_store(config)
    if store.count() == 0:
        st.info("Index a knowledge base first (Chat page explains how).")
        return

    import os

    from src.copilot.evaluation import evaluate_modes, load_probes

    probes_path = "data/eval/retrieval_probes.json"
    if not os.path.isfile(probes_path):
        st.warning(f"No probes file at `{probes_path}`.")
        return

    if st.button("Run retrieval comparison"):
        probes = load_probes(probes_path)
        retrievers = {
            m: build_retriever(config, mode=m, store=store)
            for m in constants.RETRIEVAL_MODES
        }
        metrics = evaluate_modes(retrievers, probes)
        st.dataframe(
            [
                {
                    "Mode": metrics[m].mode,
                    "term_recall@k": round(metrics[m].term_recall_at_k, 3),
                    "coverage": round(metrics[m].coverage, 3),
                    "avg_results": round(metrics[m].avg_results, 2),
                }
                for m in constants.RETRIEVAL_MODES
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(f"Over {len(probes)} probes. See docs/hybrid_search.md.")


PAGES = {
    "Chat": _page_chat,
    "Knowledge Base": _page_knowledge_base,
    "Career Tools": _page_tools,
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
    default_mode_index = (
        constants.RETRIEVAL_MODES.index(config.retrieval_mode)
        if config.retrieval_mode in constants.RETRIEVAL_MODES
        else constants.RETRIEVAL_MODES.index(constants.DEFAULT_RETRIEVAL_MODE)
    )
    st.sidebar.selectbox(
        "Retrieval mode",
        constants.RETRIEVAL_MODES,
        index=default_mode_index,
        key="retrieval_mode",
        help="hybrid (default) fuses semantic + BM25; the others are for testing.",
    )
    _render_status(config)
    PAGES[page]()


if __name__ == "__main__":
    main()
