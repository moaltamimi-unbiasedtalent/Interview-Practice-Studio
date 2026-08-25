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
from src.copilot.retrieval import build_retriever
from src.ui import shared

# Reviewer-facing starter prompts shown on an empty Chat page.
STARTER_PROMPTS = [
    "What skills are most important for this role?",
    "Analyse this job description.",
    "Compare my background with this role.",
    "What skill gaps should I prioritise?",
    "Build a 30-day preparation plan.",
    "What does the knowledge base say about this occupation?",
]


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
        with st.expander(f"Source passages ({len(results)})"):
            for index, result in enumerate(results, start=1):
                meta = result.metadata or {}
                source_type = meta.get("document_type") or "source"
                section = meta.get("section")
                locator = f"page {result.page}" if result.page is not None else section
                # Source card: title, page/section, source type, short extract.
                shared.source_card(
                    title=f"[{index}] {result.title or 'Untitled source'}",
                    source=f"{source_type}" + (f" · {locator}" if locator else ""),
                    page=None,
                    snippet=result.text,
                )


def _render_tool_executions(executions) -> None:
    if not executions:
        return
    with st.expander(f"🛠 Tools used ({len(executions)})", expanded=False):
        for ex in executions:
            mark = "✓" if ex.status == "ok" else "✗"
            st.markdown(f"{mark} **{ex.tool_name}** — `{ex.status}` ({ex.duration_seconds:.3f}s)")
            if ex.safe_result_summary:
                st.caption(ex.safe_result_summary)
            if ex.error:
                st.caption(f"error: {ex.error}")


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
        st.caption(
            "Knowledge base is empty — knowledge answers will say so. Pure-tool "
            "flows (e.g. pasting a job description below) still work."
        )

    # Optional structured context enables combined RAG + tool flows.
    with st.expander("Optional context (job description, candidate background)"):
        job_description = st.text_area("Job description", height=120, key="chat_jd")
        candidate_background = st.text_area("Candidate background", height=100, key="chat_bg")
        cols = st.columns(2)
        days = cols[0].number_input("Days until interview", 0, 365, 0, key="chat_days")
        hpw = cols[1].number_input("Hours per week", 0.0, 80.0, 0.0, key="chat_hpw")

    st.session_state.setdefault("chat_history", [])

    # Starter prompts on an empty conversation (reviewer-friendly entry points).
    if not st.session_state["chat_history"]:
        st.caption("Try a starter question:")
        cols = st.columns(2)
        for i, example in enumerate(STARTER_PROMPTS):
            if cols[i % 2].button(example, key=f"starter_{i}", use_container_width=True):
                st.session_state["career_pending_prompt"] = example
                st.rerun()

    for message in st.session_state["chat_history"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant":
                _render_sources(message.get("results", []), message.get("citations", []))
                _render_tool_executions(message.get("tool_calls", []))

    # A queued starter prompt is treated exactly like typed input.
    prompt = st.chat_input("Ask a career question…") or st.session_state.pop(
        "career_pending_prompt", None
    )
    if not prompt:
        return

    prompt = prompt.strip()[: constants.MAX_QUERY_CHARS]
    st.session_state["chat_history"].append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    from src.copilot.service import CareerIntelligenceService

    mode = st.session_state.get("retrieval_mode", config.retrieval_mode)
    retriever = build_retriever(config, mode=mode, store=store)
    service = CareerIntelligenceService(config=config, retriever=retriever)

    with st.chat_message("assistant"):
        with st.status("Understanding request…", expanded=False) as status:
            try:
                result = service.answer(
                    prompt,
                    job_description=job_description.strip() or None,
                    candidate_background=candidate_background.strip() or None,
                    days_until_interview=int(days) or None,
                    hours_per_week=float(hpw) or None,
                    progress=lambda label: status.update(label=f"{label}…"),
                )
            except Exception:  # noqa: BLE001 - never show a raw stack trace
                status.update(label="Something went wrong", state="error")
                st.error(
                    "Sorry — something went wrong preparing that answer. Please try "
                    "again, or rephrase your question."
                )
                st.session_state["chat_history"].append(
                    {
                        "role": "assistant",
                        "content": "Sorry — something went wrong. Please try again.",
                    }
                )
                return
            status.update(label="Done", state="complete")

        st.markdown(result.answer)
        _render_sources(result.retrieved, result.citations)
        _render_tool_executions(result.tool_calls)

    # Persist for re-render and for the RAG Inspector (no secrets, no prompt).
    st.session_state["chat_history"].append(
        {
            "role": "assistant",
            "content": result.answer,
            "citations": result.citations,
            "results": result.retrieved,
            "tool_calls": result.tool_calls,
        }
    )
    st.session_state["last_inspection"] = {
        "query": prompt,
        "mode": mode,
        "translated": result.response.translated_query,
        "results": result.retrieved,
        "trace": result.trace,
        "citations": result.citations,
        "tool_calls": result.tool_calls,
        "context_text": build_context(result.retrieved).context_text,
        "usage": result.response.usage,
    }

    # Safe conversation history + usage ledger (session state; no database).
    from src.copilot import history as career_history

    career_history.append_turn(st.session_state, career_history.build_turn(prompt, result))
    career_history.record_final_generation(st.session_state, result.response.usage)


# --- Knowledge Base ----------------------------------------------------------


def _render_source_sections() -> None:
    """Show the multi-source knowledge architecture (Role / Compensation / Narrative)."""
    import os

    from src.copilot.knowledge import manifest as km

    try:
        entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
    except Exception:  # pragma: no cover - manifest optional
        st.caption("No source manifest found.")
        return

    # Structured record counts (0 until the load scripts are run — no data shipped).
    role_count = comp_count = 0
    if os.path.isfile(constants.ROLE_DB_PATH):
        from src.copilot.knowledge.roles import RoleRepository

        repo = RoleRepository(constants.ROLE_DB_PATH)
        role_count = repo.counts().get("occupations", 0)
        repo.close()
    if os.path.isfile(constants.COMPENSATION_DB_PATH):
        from src.copilot.knowledge.compensation import CompensationRepository

        crepo = CompensationRepository(constants.COMPENSATION_DB_PATH)
        comp_count = crepo.count()
        crepo.close()

    def _table(rows):
        st.dataframe(
            [
                {
                    "Source": e.title,
                    "Authority": e.authority_level,
                    "Version/Year": e.version or e.reference_year or "—",
                    "Status": "manual" if e.manual_acquisition_required else "auto",
                    "Licence": "review" if e.licence_review_required else (e.licence or "—"),
                }
                for e in rows
            ],
            use_container_width=True, hide_index=True,
        )

    st.markdown("### Role & Skill Data")
    st.caption(f"Structured occupations indexed: {role_count} (run `scripts/normalise_roles.py`).")
    _table(km.by_type(entries, "occupation_taxonomy") + km.by_type(entries, "skills_taxonomy"))

    st.markdown("### Compensation Data")
    st.caption(f"Structured compensation records: {comp_count} (run `scripts/load_compensation.py`).")
    _table(km.by_type(entries, "compensation_dataset"))

    st.markdown("### Labour Market Data")
    _table(km.by_type(entries, "labour_market_forecast"))

    st.markdown("### Narrative Knowledge (vector)")
    _table(km.by_type(entries, "methodology") + km.by_type(entries, "competency_framework")
           + km.by_type(entries, "industry_report"))
    st.caption(
        "Authority level is retrieval metadata (1 official · 2 public framework · "
        "3 industry), not a truth score. No datasets are committed; see "
        "docs/knowledge_architecture.md for reproduction."
    )
    st.divider()


def _page_knowledge_base() -> None:
    st.subheader("Knowledge Base")
    _render_source_sections()
    st.markdown("### Narrative ingestion status")
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

    trace = inspection.get("trace")
    if trace is not None:
        st.markdown("**Pipeline**")
        if getattr(trace, "retrieval_lane", ""):
            st.write(f"Retrieval lane (router): `{trace.retrieval_lane}`")
        cols = st.columns(3)
        cols[0].write(f"RAG required: {'✅' if trace.rag_required else '❌'}")
        cols[1].write(f"RAG used: {'✅' if trace.rag_used else '❌'}")
        cols[2].write(f"Tools planned: {trace.tools_planned or '—'}")
        st.write(f"Tool decision (invoked): {trace.tools_invoked or '—'}")
        st.markdown("**Retrieval metrics**")
        mcols = st.columns(4)
        mcols[0].metric("Strategy", trace.retrieval_strategy or "—")
        mcols[1].metric("Queries", trace.translated_query_count)
        mcols[2].metric("Context", trace.context_count)
        mcols[3].metric("Latency (ms)", trace.retrieval_latency_ms)
        st.markdown("**Security**")
        scols = st.columns(3)
        scols[0].write(f"Input verdict: `{trace.input_verdict}`")
        scols[1].write(f"Excluded chunks: {trace.excluded_chunks}")
        scols[2].write(f"Blocked: {'🛑' if trace.blocked else '—'}")
        if trace.input_indicators:
            st.caption(f"Indicators: {', '.join(trace.input_indicators)}")
        if trace.output_findings:
            st.warning("Output guard: " + "; ".join(trace.output_findings))
        if trace.degraded:
            st.warning(f"Degraded stages: {', '.join(trace.degraded)}")
        if trace.notes:
            for note in trace.notes:
                st.caption(f"• {note}")

        st.markdown("**Hybrid channels** (rewritten query)")
        st.caption(
            "Vector (semantic) and BM25 (lexical) hits, then the fused ranking. "
            "Scores are per-channel and not directly comparable."
        )
        cols = st.columns(2)
        with cols[0]:
            st.write(f"Vector hits ({len(trace.vector_results)})")
            _results_table(trace.vector_results)
        with cols[1]:
            st.write(f"Keyword/BM25 hits ({len(trace.keyword_results)})")
            _results_table(trace.keyword_results)
        st.write(f"Fused ranking ({len(trace.fused_results)})")
        _results_table(trace.fused_results)
        if trace.evidence_sources:
            st.write("Final evidence sources:")
            for src in trace.evidence_sources:
                st.markdown(f"- {src}")

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

    citations = inspection.get("citations") or []
    st.markdown(f"**Citations ({len(citations)})**")
    if citations:
        for c in citations:
            st.markdown(f"- {c.label}")
    else:
        st.caption("No citations referenced in the answer.")

    tool_calls = inspection.get("tool_calls") or []
    st.markdown(f"**Tools called ({len(tool_calls)})**")
    if tool_calls:
        st.dataframe(
            [
                {"Tool": t.tool_name, "Status": t.status,
                 "Duration (s)": t.duration_seconds, "Result": t.safe_result_summary}
                for t in tool_calls
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.caption("No tools were called for this query.")

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

    _render_practise_this_role(ss, role_req)
    _render_tools_used()


def _render_practise_this_role(ss, role_req) -> None:
    """Offer a handoff to Interview Practice once a role has been analysed."""
    if role_req is None:
        return
    from src.integration import handoff
    from src.integration.preparation_context import build_preparation_context

    st.divider()
    st.markdown("### Practise this role")
    gap = ss.get("gap_result")
    evidence = (ss.get("last_inspection") or {}).get("results") or []
    context = build_preparation_context(
        role_requirements=role_req,
        gap_result=gap,
        evidence=evidence,
        job_description=ss.get("tool_jd") or None,
    )
    prev = handoff.preview(context)
    cols = st.columns(2)
    cols[0].write(f"**Role:** {prev['role']}")
    cols[0].write(f"**Seniority:** {prev['seniority']}")
    cols[0].write(f"**Top competencies:** {', '.join(prev['top_competencies']) or '—'}")
    cols[1].write(f"**Priority gaps:** {', '.join(prev['priority_gaps']) or '—'}")
    cols[1].write(f"**Likely interview themes:** {', '.join(prev['likely_themes']) or '—'}")
    st.caption(
        "Sends this preparation to Interview Practice to pre-fill a setup you can "
        "review and edit. It never starts an interview automatically."
    )
    if st.button("Practise this role", type="primary", key="practise_this_role"):
        handoff.request_practice(st.session_state, context)
        st.rerun()


def _render_rag_evaluation_report() -> None:
    """Show the committed RAG evaluation artifacts (honest, as-run numbers)."""
    import os

    import pandas as pd

    st.markdown("**RAG evaluation report** (Career Intelligence)")
    retr = "evaluations/retrieval_results.csv"
    tools = "evaluations/tool_selection_results.csv"
    report_md = "evaluations/rag_evaluation.md"
    if not os.path.isfile(retr):
        st.info("Run `python scripts/eval_rag.py` to generate the evaluation report.")
        return

    df = pd.read_csv(retr)
    retrieval = df[df["group"] == "retrieval"]
    st.caption("Retrieval strategies — Hit@K / MRR / Recall@K (higher is better).")
    st.dataframe(retrieval.drop(columns=["group"]), use_container_width=True, hide_index=True)
    chart = retrieval.set_index("mode")[["hit_rate@k", "mrr", "recall@k"]]
    st.bar_chart(chart)

    translation = df[df["group"] == "translation"]
    if not translation.empty:
        st.caption("Query-translation experiment — original vs translated (honest).")
        st.dataframe(translation.drop(columns=["group"]), use_container_width=True, hide_index=True)

    if os.path.isfile(tools):
        st.caption("Tool-selection accuracy (known-intent cases).")
        st.dataframe(pd.read_csv(tools), use_container_width=True, hide_index=True)

    if os.path.isfile(report_md):
        with st.expander("Full evaluation write-up (rag_evaluation.md)"):
            with open(report_md, encoding="utf-8") as handle:
                st.markdown(handle.read())
    st.divider()


def _page_evaluation() -> None:
    st.subheader("Evaluation")
    config = _config()

    # Sprint technical overview for reviewers (Advanced page — not candidate-facing).
    with st.container(border=True):
        st.markdown("**Career Intelligence — Building Applications with AI**")
        st.caption("Turing College sprint — implemented capabilities:")
        shared.badges(
            ["Advanced RAG", "LangChain", "Hybrid Search", "Tool Calling", "Query Translation"],
            tone="info",
        )
        st.caption(
            "See docs/rag.md, query_translation.md, hybrid_search.md, tool_calling.md, "
            "security.md. Inspect any query live in the RAG Inspector."
        )

    _render_rag_evaluation_report()

    st.markdown("**Live retrieval comparison (vector / keyword / hybrid)**")
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


# --- Public entry points for the Interview OS shell --------------------------
# The unified app.py owns st.set_page_config and the top-level navigation; these
# render the Career Intelligence module's pages within that shell.


def ensure_ready() -> None:
    """Load config into session and configure logging (idempotent per run)."""
    config = load_config()
    st.session_state["copilot_config"] = config
    configure_logging(debug=config.debug)


def render_sidebar() -> None:
    """Career-specific sidebar: a friendly status; technical controls are secondary."""
    config = _config()
    st.sidebar.caption(f"Model ready: {'✅' if config.is_configured else '❌ add API key'}")

    # Technical controls kept out of the way (developer/advanced).
    default_mode_index = (
        constants.RETRIEVAL_MODES.index(config.retrieval_mode)
        if config.retrieval_mode in constants.RETRIEVAL_MODES
        else constants.RETRIEVAL_MODES.index(constants.DEFAULT_RETRIEVAL_MODE)
    )
    with st.sidebar.expander("Developer settings", expanded=False):
        st.selectbox(
            "Retrieval mode",
            constants.RETRIEVAL_MODES,
            index=default_mode_index,
            key="retrieval_mode",
            help="hybrid (default) fuses semantic + BM25; the others are for testing.",
        )
        st.write(f"Model: `{config.default_model}`")
        try:
            st.write(f"Indexed chunks: {_get_store(config).count()}")
        except Exception:  # pragma: no cover - defensive UI guard
            st.write("Indexed chunks: unavailable")
        st.caption(f"Vector store: `{config.chroma_persist_dir}`")

    # Preparation handoff: show + allow clearing an active PreparationContext.
    from src.integration import handoff

    if handoff.has_context(st.session_state):
        st.sidebar.divider()
        st.sidebar.caption("Preparation context is active (sent to Interview Practice).")
        if st.sidebar.button("Clear preparation context"):
            handoff.clear_context(st.session_state)
            st.rerun()


def _render_usage_diagnostics() -> None:
    """Optional, collapsed usage/history/export panel (hidden by default)."""
    from src.copilot import history as career_history
    from src.integration import export as combined_export
    from src.integration import handoff

    ss = st.session_state
    hist = career_history.get_history(ss)
    ledger = career_history.get_ledger(ss)
    if not hist.turns and not ledger.records:
        return

    with st.expander("Usage & diagnostics", expanded=False):
        st.caption("Session-only. Career and Interview usage are tracked separately.")
        by_source = ledger.tokens_by_source()
        st.write({"tokens_by_operation": by_source, "total_tokens": ledger.total_tokens})
        has_cost = any(r.cost_usd is not None for r in ledger.records)
        st.write(
            f"Estimated cost: ${ledger.total_cost_usd:.4f}" if has_cost else "Cost unavailable"
        )

        if hist.turns and hist.turns[-1].rag:
            st.markdown("**Last turn retrieval**")
            st.write(hist.turns[-1].rag.model_dump())

        st.markdown("**Export**")
        cols = st.columns(3)
        cols[0].download_button(
            "Conversation JSON", data=hist.to_json(),
            file_name="career_conversation.json", mime="application/json",
            disabled=not hist.turns,
        )
        cols[1].download_button(
            "Conversation CSV", data=hist.to_csv(),
            file_name="career_conversation.csv", mime="text/csv",
            disabled=not hist.turns,
        )
        combined = combined_export.combined_session_json(
            preparation=handoff.get_context(ss),
            career_history=hist,
            interview_report=handoff.get_interview_summary(ss),
        )
        cols[2].download_button(
            "Combined session JSON", data=combined,
            file_name="interview_os_session.json", mime="application/json",
        )
        if st.button("Clear conversation history"):
            career_history.clear_history(ss)
            st.rerun()


def render_career() -> None:
    """The Career Intelligence landing: header + Chat / Career Tools."""
    _render_header(_config())
    section = st.radio(
        "Career section", ["Chat", "Career Tools"], horizontal=True, key="career_section"
    )
    if section == "Chat":
        _page_chat()
        _render_usage_diagnostics()
    else:
        _page_tools()


def render_knowledge_base() -> None:
    _page_knowledge_base()


def render_rag_inspector() -> None:
    _page_rag_inspector()


def render_evaluation() -> None:
    _page_evaluation()
