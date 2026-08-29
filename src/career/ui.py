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
from src.copilot.embeddings import embedding_status
from src.copilot.logging_utils import configure_logging
from src.copilot.retrieval.adaptive import dominant_signal
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

    # Embedding quality mode — honest about semantic vs lexical retrieval.
    status = embedding_status(config)
    if status["quality_mode"] == "SEMANTIC":
        st.sidebar.write(f"Embeddings: ✅ SEMANTIC (`{status['model']}`)")
    else:
        st.sidebar.write("Embeddings: ⚠ OFFLINE LEXICAL")
        st.sidebar.caption(
            "No semantic embedding credential configured — retrieval uses a "
            "local lexical (hash) embedder. Answers are grounded in real "
            "sources, but semantic similarity is approximate. Set "
            "`COPILOT_EMBEDDING_API_KEY` for semantic retrieval."
        )


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


def _result_source_url(result) -> str | None:
    """Public URL for a retrieved chunk (explicit metadata or manifest lookup)."""
    meta = result.metadata or {}
    url = meta.get("source_url")
    if url:
        return url
    try:
        from src.copilot.knowledge.manifest import url_for_source

        return url_for_source(meta.get("manifest_source_id") or meta.get("source_id"))
    except Exception:  # pragma: no cover - manifest optional
        return None


def _render_sources(results, citations) -> None:
    # Always surface the sources behind an answer. Prefer the model's inline
    # citations; if the model grounded its answer on retrieved evidence but did
    # not emit [n] markers, still list the passages it was given so the source is
    # never hidden.
    if citations:
        st.markdown("**Sources**")
        for citation in citations:
            st.markdown(citation.label)
    elif results:
        st.markdown("**Sources consulted**")
        for index, result in enumerate(results, start=1):
            title = result.title or result.source or "Untitled source"
            url = _result_source_url(result)
            linked = f"[{title}]({url})" if url else title
            locator = f" — page {result.page}" if result.page is not None else ""
            st.markdown(f"[{index}] {linked}{locator}")

    if results:
        with st.expander(f"Source passages ({len(results)})"):
            for index, result in enumerate(results, start=1):
                meta = result.metadata or {}
                source_type = meta.get("document_type") or "source"
                section = meta.get("section")
                locator = f"page {result.page}" if result.page is not None else section
                url = _result_source_url(result)
                # Source card: title, page/section, source type, short extract.
                shared.source_card(
                    title=f"[{index}] {result.title or 'Untitled source'}",
                    source=f"{source_type}" + (f" · {locator}" if locator else ""),
                    page=None,
                    snippet=result.text,
                )
                if url:
                    st.markdown(f"[Open source ↗]({url})")


def _extract_upload_text(upload) -> tuple[str, str] | None:
    """Extract (title, text) from a Streamlit upload via the ingestion loaders."""
    import os
    import tempfile

    from src.copilot.ingestion.loaders import LoaderError, load_document

    suffix = os.path.splitext(upload.name)[1] or ".txt"
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(upload.getvalue())
            path = tmp.name
        units = load_document(path)
        text = "\n".join(u.text for u in units)
        return (upload.name, text)
    except (LoaderError, Exception):  # noqa: BLE001 - a bad upload never breaks the page
        return None
    finally:
        try:
            os.unlink(path)
        except Exception:  # noqa: BLE001
            pass


def _render_company_context_input():
    """Optional Company Context section — builds a time-stamped CompanyContext.

    Company research is kept separate from the permanent occupational KB and is
    never persisted into it. Returns a CompanyContext or None.
    """
    from src.copilot.company import build_company_context

    with st.expander("Company context (optional — for company-specific prep)"):
        st.caption(
            "Time-sensitive employer research from sources you trust. Kept separate "
            "from the occupational knowledge base and never treated as an "
            "occupational fact. Uploaded/pasted text is scanned for injection."
        )
        name = st.text_input("Company name", key="co_name")
        cols = st.columns(2)
        website = cols[0].text_input("Official website URL", key="co_site")
        careers = cols[1].text_input("Careers page URL", key="co_careers")
        industry = st.text_input("Industry (optional)", key="co_industry")
        uploads = st.file_uploader(
            "Upload company materials (annual report, investor deck, press release)",
            type=["pdf", "txt", "md", "csv"], accept_multiple_files=True, key="co_docs")
        if not name.strip():
            return None
        docs = []
        for up in uploads or []:
            got = _extract_upload_text(up)
            if got:
                docs.append(got)
        ctx = build_company_context(
            name.strip(), official_website=website or None, career_page=careers or None,
            industry=industry or None, documents=docs or None)
        # Show source links + recency, honestly.
        if ctx.source_references:
            st.markdown("**Sources**")
            for s in ctx.source_references:
                label = s.url or s.title or "source"
                link = f"[{label}]({s.url})" if s.url else label
                st.markdown(f"- {link} — `{s.source_type}`"
                            + (f" · {s.publication_date}" if s.publication_date else ""))
        st.caption(f"Retrieved at {ctx.retrieved_at}. Company facts are time-sensitive.")
        for note in ctx.notes:
            st.caption(f"⚠ {note}")
        return ctx


def _render_product_readiness() -> None:
    """Production readiness by coverage area (READY / PARTIAL / MISSING)."""
    import json
    import os

    path = "data/metrics.json"
    if not os.path.isfile(path):
        st.caption("Run `python scripts/gen_metrics.py` for production-readiness by area.")
        return
    try:
        areas = json.load(open(path, encoding="utf-8")).get("readiness_by_area", [])
    except Exception:  # noqa: BLE001
        return
    if not areas:
        return
    badge = {"READY": "🟢 READY", "PARTIAL": "🟡 PARTIAL", "MISSING": "🔴 MISSING"}
    with st.expander("Production readiness by coverage area", expanded=False):
        st.dataframe(
            [{"Coverage area": a["area"], "Status": badge.get(a["status"], a["status"]),
              "Detail": a.get("detail", "")} for a in areas],
            use_container_width=True, hide_index=True, height=340)
        st.caption("READY = real official data loaded · PARTIAL = present but "
                   "fixture/coarse/partial-geo · MISSING = no data. From "
                   "`data/metrics.json` (scripts/gen_metrics.py).")


def _render_structured_facts(evidence) -> None:
    """OPT-3C: surface key structured facts (currency/period/year/geo) visibly.

    Compensation and labour-market context is shown in a small panel rather than
    being buried inside a metadata expander.
    """
    if not evidence:
        return
    comp = [e for e in evidence if getattr(e, "evidence_type", "") == "compensation"]
    labour = [e for e in evidence
              if getattr(e, "evidence_type", "") in ("forecast", "openings", "shortage", "vacancy")]
    if not comp and not labour:
        return
    with st.expander("Structured facts (context)", expanded=bool(comp)):
        if comp:
            st.markdown("**Compensation**")
            st.dataframe(
                [{"Occupation": e.occupation_title or "—",
                  "Statistic": (e.metadata or {}).get("statistic", "—"),
                  "Value": e.text.split(":", 1)[-1].strip()[:40] if ":" in e.text else "—",
                  "Currency": (e.metadata or {}).get("currency", "—"),
                  "Pay period": (e.metadata or {}).get("pay_period", "—"),
                  "Geography": e.country or e.geography or "—",
                  "Year": e.reference_year or "—",
                  "Source": e.source_title or e.source_id} for e in comp[:8]],
                use_container_width=True, hide_index=True)
        if labour:
            st.markdown("**Labour market**")
            st.dataframe(
                [{"Type": e.evidence_type, "Occupation": e.occupation_title or "—",
                  "Geography": e.country or e.geography or "—",
                  "Year/Period": e.reference_year or "—",
                  "Source": e.source_title or e.source_id,
                  "Detail": e.text[:70]} for e in labour[:8]],
                use_container_width=True, hide_index=True)
        st.caption("Figures keep their currency/period/statistic/geography/year — "
                   "never compared across contexts.")


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
        # Match the Career Tools "Hours per week" input exactly (min 1.0, value 6.0).
        hpw = cols[1].number_input(
            "Hours per week", min_value=1.0, max_value=80.0, value=6.0, key="chat_hpw"
        )

    company_context = _render_company_context_input()
    if company_context is not None:
        # Carry a safe summary for the interview handoff (never raw files).
        st.session_state["company_context_summary"] = company_context.safe_summary()

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
                _render_structured_facts(message.get("evidence", []))
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

    from src.copilot.knowledge.retrieval import build_default_coordinator
    from src.copilot.service import CareerIntelligenceService

    mode = st.session_state.get("retrieval_mode", config.retrieval_mode)
    retriever = build_retriever(config, mode=mode, store=store)
    # Production: wire the real structured stores into the chat answer.
    coordinator = build_default_coordinator(config)
    service = CareerIntelligenceService(
        config=config, retriever=retriever, knowledge_coordinator=coordinator
    )

    with st.chat_message("assistant"):
        with st.status("Understanding request…", expanded=False) as status:
            try:
                result = service.answer(
                    prompt,
                    job_description=job_description.strip() or None,
                    candidate_background=candidate_background.strip() or None,
                    days_until_interview=int(days) or None,
                    hours_per_week=float(hpw) or None,
                    company_context=company_context,
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
        _render_structured_facts(result.response.evidence)
        _render_sources(result.retrieved, result.citations)
        _render_tool_executions(result.tool_calls)

    # Persist for re-render and for the RAG Inspector (no secrets, no prompt).
    st.session_state["chat_history"].append(
        {
            "role": "assistant",
            "content": result.answer,
            "citations": result.citations,
            "results": result.retrieved,
            "evidence": result.response.evidence,
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
    """Multi-source knowledge architecture with measured lifecycle status.

    Every row shows the *measured* local state (record count + lifecycle badge)
    derived from what is actually on disk — a source in the manifest is never
    implied to be loaded. Grouped by data type so structured vs narrative lanes
    are visible at a glance.
    """
    from src.copilot.knowledge import manifest as km
    from src.copilot.knowledge import status as kstatus

    try:
        entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
    except Exception:  # pragma: no cover - manifest optional
        st.caption("No source manifest found.")
        return

    statuses = {s.source_id: s for s in kstatus.compute_status(constants.SOURCE_MANIFEST_PATH)}
    health = kstatus.summary(list(statuses.values()))

    # --- Knowledge Health dashboard (measured, honest) ---
    import os as _os

    st.markdown("### Knowledge Health")
    cols = st.columns(4)
    cols[0].metric("Configured sources", health["configured"])
    cols[1].metric("Real-data sources", health["real_data_sources"])
    cols[2].metric("Production-ready (real)", health["production_ready"])
    cols[3].metric("Fixture-only", health["fixture_only"])
    cols = st.columns(4)
    cols[0].metric("Local files found", health["local_file_found"])
    cols[1].metric("Structured records", f"{health['structured_records']:,}")
    cols[2].metric("Vector chunks", f"{health['vector_chunks']:,}")
    cols[3].metric("Licence review", health["licence_review"])

    # Last refresh (from the generated status file) + missing critical sources.
    status_path = constants.SOURCE_STATUS_PATH
    last = None
    if _os.path.isfile(status_path):
        import datetime as _dt
        last = _dt.datetime.fromtimestamp(_os.path.getmtime(status_path)).strftime("%Y-%m-%d %H:%M")
    missing = [e.title for e in entries
               if not (statuses.get(e.source_id) and
                       (statuses[e.source_id].available_for_retrieval
                        or statuses[e.source_id].local_file_found))]
    cap = (f"Last refreshed: {last or 'unknown'} · Manual-acquisition outstanding: "
           f"{health['manual_acquisition']} · Licence-review outstanding: "
           f"{health['licence_review']}. ")
    if missing:
        cap += "Missing (configured, not found locally): " + ", ".join(missing) + ". "
    cap += ("**Available for retrieval** is anything loaded locally; "
            "**production-ready** is real official data with a clear licence — "
            "synthetic fixtures are never production-ready.")
    st.caption(cap)

    _render_product_readiness()

    def _tick(v):
        return "✓" if v else "✗"

    def _origin_badge(s) -> str:
        if not s or not s.data_origin:
            return "—"
        if s.fixture_only:
            return "🧪 FIXTURE DATA"
        return "🟢 REAL DATA"

    def _prod_badge(s) -> str:
        if not s or not s.available_for_retrieval:
            return "—"
        return "✅ PRODUCTION READY" if s.production_ready else "⛔ NOT PRODUCTION READY"

    def _row(e):
        s = statuses.get(e.source_id)
        return {
            "Source": e.title,
            "Auth": e.authority_level,
            "Region": e.region or e.country or "—",
            "Local file": _tick(s.local_file_found) if s else "✗",
            "Records": s.record_count if s else 0,
            "Origin": (s.data_origin or "—") if s else "—",
            "Data": _origin_badge(s),
            "Production": _prod_badge(s),
            "Lifecycle": s.lifecycle if s else "CONFIGURED",
            "Licence": "review" if e.licence_review_required else (e.licence or "—"),
            "Source link": e.source_url or "",
        }

    # Render the source URL as a clickable link (falls back to plain text on
    # older Streamlit versions that lack LinkColumn).
    try:
        link_col = st.column_config.LinkColumn("Source link", display_text="Open ↗")
        column_config = {"Source link": link_col}
    except Exception:  # pragma: no cover - column_config unavailable
        column_config = None

    for group_id, group_label in km.GROUPS:
        rows = km.by_group(entries, group_id)
        if not rows:
            continue
        st.markdown(f"### {group_label}")
        st.dataframe(
            [_row(e) for e in rows],
            use_container_width=True,
            hide_index=True,
            column_config=column_config,
        )

    st.caption(
        "Authority level is retrieval metadata (1 official · 2 public framework · "
        "3 industry), not a truth score. No third-party datasets are committed; "
        "run the load scripts against acquired sources — see "
        "docs/rebuild_knowledge_base.md and docs/source_licensing.md."
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

        # Structured multi-lane retrieval transparency.
        if (getattr(trace, "structured_queries", None)
                or getattr(trace, "resolved_occupation", "")
                or getattr(trace, "detected_country", None)):
            st.markdown("**Structured retrieval**")
            scols = st.columns(3)
            scols[0].write(f"Country detected: `{trace.detected_country or '—'}`")
            scols[1].write(f"Occupation: `{trace.resolved_occupation or '—'}`")
            scols[2].metric("Structured records", trace.structured_record_count)
            if trace.occupation_candidates:
                st.caption("Candidates considered: " + ", ".join(trace.occupation_candidates[:6]))
            if trace.source_precedence:
                st.caption("Source precedence: " + " → ".join(trace.source_precedence))
            if trace.sources_considered:
                st.caption("Sources returned: " + ", ".join(trace.sources_considered))
            if trace.structured_queries:
                st.write("Structured queries:")
                for q in trace.structured_queries:
                    st.code(q, language="text")
            if trace.coverage_notes:
                for note in trace.coverage_notes:
                    st.caption(f"⚠ {note}")
        st.markdown("**Retrieval metrics**")
        mcols = st.columns(4)
        mcols[0].metric("Strategy", trace.retrieval_strategy or "—")
        mcols[1].metric("Queries", trace.translated_query_count)
        mcols[2].metric("Context", trace.context_count)
        mcols[3].metric("Latency (ms)", trace.retrieval_latency_ms)

        # Hybrid calibration (OPT-2): effective weights + dominant signal.
        if (trace.retrieval_strategy or "").lower() == "hybrid":
            st.markdown("**Hybrid calibration**")
            wcols = st.columns(4)
            wcols[0].metric("Vector weight", getattr(trace, "effective_vector_weight", "—"))
            wcols[1].metric("Keyword weight", getattr(trace, "effective_keyword_weight", "—"))
            wcols[2].metric("Weighting", getattr(trace, "weight_strategy", "—") or "—")
            wcols[3].metric("Reranker", getattr(trace, "reranker_provider", "none") or "none")
            reason = getattr(trace, "weight_reason_code", "")
            if reason:
                st.caption(f"Weight signal: `{reason}`")
            if getattr(trace, "reranker_used", False):
                st.caption(
                    f"Reranked {getattr(trace, 'reranked_count', 0)} candidate(s) in "
                    f"{getattr(trace, 'reranker_latency_ms', 0)} ms."
                )
        if getattr(trace, "quality_mode", ""):
            st.caption(f"Quality mode: `{trace.quality_mode}`")

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
        if trace.vector_results or trace.keyword_results:
            st.caption(
                "Dominant signal: "
                + dominant_signal(trace.vector_results, trace.keyword_results,
                                  trace.fused_results)
            )
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
        company_context=ss.get("company_context_summary") or None,
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


def _render_expanded_report() -> None:
    """Baseline (11R) vs Expanded architecture (11R-A). Shows results if present."""
    import os

    import pandas as pd

    st.markdown("**Expanded Career Intelligence** (11R-A: structured role / compensation / routing)")
    path = "evaluations/expanded_architecture_results.csv"
    if not os.path.isfile(path):
        st.caption(
            "11R established the baseline benchmark (above). 11R-A adds the "
            "evaluation hooks (router / structured-role / compensation / provenance) "
            "and labelled datasets under `evaluations/`. Run "
            "`python scripts/eval_expanded.py` to produce the extended report "
            "(it never overwrites the 11R baseline)."
        )
        st.divider()
        return

    df = pd.read_csv(path)
    for group, label in [
        ("router", "Routing accuracy"),
        ("structured_role", "Structured role retrieval"),
        ("compensation", "Compensation retrieval"),
        ("retrieval_diff_vs_baseline", "Core retrieval Δ vs 11R baseline (worse = negative)"),
    ]:
        sub = df[df["group"] == group]
        if not sub.empty:
            st.caption(label)
            st.dataframe(sub.drop(columns=["group"]), use_container_width=True, hide_index=True)
    st.divider()


def _render_product_coverage() -> None:
    """CI-PH4 product-coverage benchmark (reviewer/developer view)."""
    import csv
    import os
    from collections import Counter, defaultdict

    results = "evaluations/product_coverage/results.csv"
    if not os.path.isfile(results):
        st.caption(
            "No product-coverage run found. Generate cases with "
            "`python scripts/gen_product_coverage_cases.py` then run "
            "`python scripts/eval_product_coverage.py`."
        )
        st.divider()
        return

    rows = list(csv.DictReader(open(results, encoding="utf-8")))

    def _rate(rs, key):
        vals = [r[key] for r in rs if r[key] not in ("", "None")]
        return (sum(1 for v in vals if v == "True") / len(vals)) if vals else None

    st.caption(f"{len(rows)} labelled candidate questions over production-ready real "
               "sources. Deterministic; offline/lexical unless a dedicated embedding "
               "key is configured. Acceptance gates, not pre-existing claims.")

    gates = {"routing_ok": ("Routing", 0.95), "geo_ok": ("Geo source", 0.95),
             "hit@5_ok": ("Evidence Hit@5", 0.90), "citation_ok": ("Citation validity", 1.0),
             "salary_ok": ("Salary context", 1.0), "tool_ok": ("Tool selection", 0.95),
             "insufficient_ok": ("Insufficient-evidence", 0.95)}
    metric_rows = []
    for key, (label, gate) in gates.items():
        r = _rate(rows, key)
        metric_rows.append({"Metric": label, "Score": f"{r:.0%}" if r is not None else "n/a",
                            "Gate": f"{gate:.0%}", "Pass": "✅" if (r is not None and r >= gate) else "❌"})
    st.dataframe(metric_rows, use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Coverage by question family**")
        byfam = defaultdict(list)
        for r in rows:
            byfam[r["question_family"]].append(r)
        fam_rows = []
        for fam in sorted(byfam):
            hv = [x["hit@5_ok"] for x in byfam[fam] if x["hit@5_ok"] not in ("", "None")]
            cov = (sum(1 for v in hv if v == "True") / len(hv)) if hv else None
            fam_rows.append({"Family": fam, "Cases": len(byfam[fam]),
                             "Covered": f"{cov:.0%}" if cov is not None else "n/a"})
        st.dataframe(fam_rows, use_container_width=True, hide_index=True, height=280)
    with c2:
        st.markdown("**Coverage by geography**")
        bygeo = defaultdict(list)
        for r in rows:
            if r["geography"]:
                bygeo[r["geography"]].append(r)
        geo_rows = []
        for g in sorted(bygeo):
            geo_rows.append({"Geo": g, "Cases": len(bygeo[g]),
                             "Geo-source": f"{_rate(bygeo[g], 'geo_ok'):.0%}"})
        st.dataframe(geo_rows, use_container_width=True, hide_index=True)
        st.markdown("**Source routing**")
        src = Counter()
        for r in rows:
            for s in filter(None, r["sources"].split("|")):
                src[s] += 1
        st.dataframe([{"Source": s, "Cases": n} for s, n in src.most_common()],
                     use_container_width=True, hide_index=True, height=180)

    fails = sum(1 for r in rows if any(
        r[k] == "False" for k in ("routing_ok", "geo_ok", "hit@5_ok", "citation_ok",
                                  "salary_ok", "tool_ok", "insufficient_ok")))
    st.caption(f"{fails} case(s) with at least one failed check — see "
               "`evaluations/product_coverage/failures.md` for the ranked remediation list.")
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

    st.markdown("#### Product Coverage (CI-PH4)")
    _render_product_coverage()
    st.markdown("#### Baseline RAG (11R)")
    _render_rag_evaluation_report()
    st.markdown("#### Expanded architecture (11R-A)")
    _render_expanded_report()

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
