"""CareerIntelligenceService — the single orchestration layer.

Combines advanced RAG and domain tool calling into one explainable, non-autonomous
LangChain workflow so the Streamlit layer calls a domain service instead of wiring
retrieval, translation and tools itself:

    input validation -> intent understanding -> query translation
    -> retrieval requirement -> hybrid retrieval -> tool requirement
    -> tool execution -> bounded (trust-separated) context -> OpenRouter
    -> grounded response (citations + tools used)

Every stage has a controlled fallback: a failure degrades the result and is
recorded in the trace — it never crashes the Streamlit session.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from src.copilot import constants
from src.copilot.cache import TTLCache
from src.copilot.config import CopilotConfig
from src.copilot.models import (
    ChatResponse,
    Citation,
    KnowledgeEvidence,
    RetrievalResult,
    ToolExecution,
    TranslatedQuery,
)
from src.copilot.rag.responder import Responder
from src.copilot.rag.routing import route_for_intent
from src.copilot.rag.synthesis import build_evidence_messages
from src.copilot.rag.translation import QueryTranslator
from src.copilot.retrieval.fusion import reciprocal_rank_fusion
from src.copilot.retrieval.hybrid import HybridRetriever
from src.copilot.retrieval.keyword import KeywordRetriever
from src.copilot.retrieval.vector import VectorRetriever
from src.copilot.security import guard_output, scan_text, screen_results, validate_input
from src.copilot.tools import ToolInvoker, build_tool_registry

_REFUSAL_MESSAGE = (
    "I can't help with that request — it appears to try to override my "
    "instructions or access protected information. I can help with career "
    "guidance, job analysis and interview preparation."
)

__all__ = ["CareerIntelligenceService", "OrchestrationResult", "PipelineTrace"]

_MARKER_RE = re.compile(r"\[(\d+)\]")


@dataclass
class PipelineTrace:
    """Safe, inspector-facing trace of the pipeline (no hidden reasoning)."""

    intent: str = "other"
    rag_required: bool = False
    rag_used: bool = False
    tools_planned: list[str] = field(default_factory=list)
    tools_invoked: list[str] = field(default_factory=list)
    degraded: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    vector_results: list[RetrievalResult] = field(default_factory=list)
    keyword_results: list[RetrievalResult] = field(default_factory=list)
    fused_results: list[RetrievalResult] = field(default_factory=list)
    evidence_sources: list[str] = field(default_factory=list)
    # Retrieval lane chosen by the knowledge router (drives structured retrieval).
    retrieval_lane: str = ""
    # Structured multi-lane retrieval (inspector).
    detected_country: str | None = None
    resolved_occupation: str = ""
    occupation_candidates: list[str] = field(default_factory=list)
    sources_considered: list[str] = field(default_factory=list)
    source_precedence: list[str] = field(default_factory=list)
    structured_queries: list[str] = field(default_factory=list)
    structured_record_count: int = 0
    coverage_notes: list[str] = field(default_factory=list)
    # RAG metrics (safe; counts + latency only).
    retrieval_strategy: str = ""
    translated_query_count: int = 0
    context_count: int = 0
    retrieval_latency_ms: float = 0.0
    # Hybrid calibration + reranker (OPT-1B/OPT-2) — safe labels only.
    effective_vector_weight: float = 0.0
    effective_keyword_weight: float = 0.0
    weight_strategy: str = "default_equal"
    weight_reason_code: str = "DEFAULT_EQUAL"
    reranker_used: bool = False
    reranker_provider: str = "none"
    reranked_count: int = 0
    reranker_latency_ms: float = 0.0
    # Caching + cost mode (OPT-4).
    translation_cache_hit: bool = False
    structured_cache_hit: bool = False
    quality_mode: str = "balanced"
    # Security.
    input_verdict: str = "allow"
    input_indicators: list[str] = field(default_factory=list)
    blocked: bool = False
    excluded_chunks: int = 0
    output_findings: list[str] = field(default_factory=list)


@dataclass
class PipelinePlan:
    """A dry-run description of what a query *would* trigger — no LLM, no cost.

    Built entirely from deterministic heuristics (heuristic translation, the
    regex router, the fixed intent→route table) so the user can preview the
    intended steps before spending a synthesis call.
    """

    query: str
    intent: str
    retrieval_lane: str
    lane_reason: str
    detected_country: str | None
    rag_required: bool
    tools_planned: list[str] = field(default_factory=list)
    tools_expected_to_run: list[str] = field(default_factory=list)
    tools_skipped_no_input: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class PreparationArtifacts:
    """Typed, ephemeral tool outputs kept for the Career → Interview handoff.

    These are the *raw* typed results the Chat pipeline already computed (role
    requirements, gap analysis, preparation plan, question set). They are
    deliberately kept OFF :class:`ChatResponse` so they are never logged,
    serialised into chat history, surfaced in the RAG Inspector, added to usage
    logs, or placed in the safe ToolExecution summaries — they are session /
    handoff state only, consumed to build a ``PreparationContext``.
    """

    role_requirements: object | None = None
    gap_result: object | None = None
    preparation_plan: object | None = None
    question_set: object | None = None

    def is_empty(self) -> bool:
        return not any((self.role_requirements, self.gap_result,
                        self.preparation_plan, self.question_set))


@dataclass
class ToolRunOutcome:
    """Internal return contract for :meth:`_run_tools`."""

    executions: list = field(default_factory=list)
    summaries: list = field(default_factory=list)
    artifacts: PreparationArtifacts = field(default_factory=PreparationArtifacts)


@dataclass
class OrchestrationResult:
    """The service's result: a grounded response plus the pipeline trace.

    ``preparation_artifacts`` carries typed handoff state (see
    :class:`PreparationArtifacts`); it is never merged into ``response``.
    """

    response: ChatResponse
    trace: PipelineTrace
    preparation_artifacts: PreparationArtifacts | None = None

    @property
    def answer(self) -> str:
        return self.response.answer

    @property
    def citations(self):
        return self.response.citations

    @property
    def retrieved(self):
        return self.response.retrieved

    @property
    def tool_calls(self):
        return self.response.tool_calls


class CareerIntelligenceService:
    """Domain service that orchestrates RAG + tools into one grounded answer."""

    def __init__(
        self,
        *,
        config: CopilotConfig | None = None,
        retriever=None,
        translator: QueryTranslator | None = None,
        tool_invoker: ToolInvoker | None = None,
        synthesis_responder: Responder | None = None,
        knowledge_coordinator=None,
        translation_cache: TTLCache | None = None,
        top_k: int = constants.DEFAULT_TOP_K,
        max_context_chars: int = constants.MAX_CONTEXT_CHARS,
    ) -> None:
        self.config = config
        self.retriever = retriever
        self.translator = translator or QueryTranslator(config=config)
        self.tool_invoker = tool_invoker or ToolInvoker(build_tool_registry(config=config))
        self._synthesis_responder = synthesis_responder
        # Structured retrieval is injected: production (UI/new tests) provides a
        # coordinator over the real/fixture stores; when absent the service runs
        # the existing vector-only path unchanged (keeps prior tests hermetic).
        self.knowledge_coordinator = knowledge_coordinator
        # Quality/cost mode: "quality" (freshest, cache bypassed), "balanced"
        # (default), or "cheap" (smaller top-k, cache on). Unknown -> balanced.
        mode = (getattr(config, "quality_mode", "balanced") or "balanced").lower()
        self.quality_mode = mode if mode in ("quality", "balanced", "cheap") else "balanced"
        if self.quality_mode == "cheap":
            top_k = max(1, min(top_k, constants.CHEAP_MODE_TOP_K))
        self.top_k = top_k
        self.max_context_chars = max_context_chars
        # Session-scoped TTL cache for deterministic translation reuse (OPT-4).
        # A caller (Streamlit) may inject a cache that outlives per-query service
        # instances; otherwise we build a fresh, instance-local one.
        if translation_cache is not None:
            self._translation_cache = translation_cache
        else:
            ttl = getattr(config, "query_cache_ttl_seconds", 300) if config else 300
            cap = getattr(config, "query_cache_max_entries", 256) if config else 256
            self._translation_cache = TTLCache(ttl_seconds=ttl, max_entries=cap)

    # -- public API --------------------------------------------------------

    def answer(
        self,
        query: str,
        *,
        job_description: str | None = None,
        candidate_background: str | None = None,
        days_until_interview: int | None = None,
        hours_per_week: float | None = None,
        question_focus: list[str] | None = None,
        company_context=None,
        model: str | None = None,
        progress=None,
    ) -> OrchestrationResult:
        trace = PipelineTrace()

        def _step(label: str) -> None:
            if progress is not None:
                try:
                    progress(label)
                except Exception:  # pragma: no cover - progress must never break the run
                    pass

        _step("Understanding request")
        # 1) Input validation + injection scan (untrusted user input).
        validation = validate_input(query or "", "query")
        trace.notes.extend(validation.notes)
        if not validation.ok:
            return self._plain_result(validation.error or "Please enter a question.", trace)
        query = validation.cleaned

        scan = scan_text(query)
        trace.input_verdict = scan.verdict
        trace.input_indicators = scan.indicators
        if scan.blocked:
            trace.blocked = True
            trace.notes.append(
                "User input blocked by the injection guard: " + ", ".join(scan.indicators)
            )
            return self._plain_result(_REFUSAL_MESSAGE, trace)
        if scan.flagged:
            trace.notes.append(
                "User input flagged (allowed with warning): " + ", ".join(scan.indicators)
            )

        # Untrusted structured inputs: validate + scan; drop any that are attacks.
        job_description = self._sanitize_context(
            job_description, "job_description", "Job description", trace
        )
        candidate_background = self._sanitize_context(
            candidate_background, "candidate_background", "Candidate background", trace
        )

        # Knowledge-router lane classification — this now drives real structured
        # retrieval (roles/compensation/competency/labour-market) alongside vector
        # RAG, not just inspector classification.
        from src.copilot.knowledge.router import detect_country, route_question

        route_decision = route_question(query)
        trace.retrieval_lane = route_decision.lane
        trace.detected_country = detect_country(query)

        # 2) Intent understanding + 3) query translation (fallback built in).
        # Session TTL cache: translation is deterministic for a given query, so a
        # re-ask reuses it (bypassed in "quality" mode for maximum freshness).
        _step("Translating query")
        trace.quality_mode = self.quality_mode
        cache_key = query.strip().lower()
        translated = None
        if self.quality_mode != "quality":
            hit, cached = self._translation_cache.get(cache_key)
            if hit:
                translated = cached
                trace.translation_cache_hit = True
        if translated is None:
            translated = self.translator.translate(query)
            if self.quality_mode != "quality":
                self._translation_cache.set(cache_key, translated)
        trace.intent = translated.intent
        if translated.strategy in ("heuristic", "fallback"):
            trace.degraded.append("translation")
            trace.notes.append("Query translation degraded; used heuristic understanding.")

        # 4) Route: does this need RAG, tools, both or neither?
        route = route_for_intent(translated.intent)
        rag_required = route.rag_required and translated.retrieval_required
        trace.rag_required = rag_required
        trace.tools_planned = list(route.tools)

        # 5) Hybrid retrieval (controlled).
        results: list[RetrievalResult] = []
        if rag_required:
            _step("Searching knowledge base")
            trace.translated_query_count = len(translated.all_queries)
            started = time.perf_counter()
            results = self._retrieve(translated, trace)
            trace.retrieval_latency_ms = round((time.perf_counter() - started) * 1000, 2)
            _step("Combining results")
            # RAG guard: retrieved chunks are untrusted; drop injected ones.
            screen = screen_results(results)
            if screen.excluded or screen.warned:
                trace.notes.append(screen.summary())
                trace.excluded_chunks = screen.excluded_count
            results = screen.kept
            if not results and trace.rag_used:
                trace.rag_used = False
            # 5a) Optional reranking (OPT-1B): RRF candidates → reranker → top-k.
            results = self._maybe_rerank(query, results, trace)

        # Record effective hybrid weights + dominant-signal (OPT-2).
        self._record_weight_trace(query, trace)

        trace.context_count = len(results)

        # 5b) Structured multi-lane retrieval (injected coordinator). Runs the
        # real stores for the router's lane; empty when no coordinator (prior
        # tests) or lane VECTOR.
        structured_evidence, coverage_notes = self._structured_retrieval(
            route_decision, query, trace
        )

        # If the occupation is genuinely ambiguous, ask to clarify rather than
        # guessing — but only for a pure structured question (no vector evidence,
        # no tools planned) so we never suppress an otherwise-answerable turn.
        clarify_msg = getattr(self, "_clarify_message", None)
        self._clarify_message = None
        if clarify_msg and not results and not route.tools:
            return self._plain_result(clarify_msg, trace)

        # 6) Tool requirement + 7) tool execution (controlled).
        if route.tools:
            _step("Running tools")
        tool_outcome = self._run_tools(
            route,
            trace,
            job_description=job_description,
            candidate_background=candidate_background,
            days_until_interview=days_until_interview,
            hours_per_week=hours_per_week,
            question_focus=question_focus,
            results=results,
        )
        tool_execs = tool_outcome.executions
        tool_summaries = tool_outcome.summaries

        # 8) Assemble unified, numbered evidence (structured first, then narrative)
        # into trust-separated sections; build matching citations.
        evidence, sections, citations = self._assemble_evidence(structured_evidence, results)
        trace.evidence_sources = [c.label for c in citations]

        # 9) OpenRouter synthesis over the multi-section evidence.
        _step("Preparing response")
        company_summary = None
        if company_context is not None:
            try:
                company_summary = company_context.safe_summary()
                trace.notes.append("Company context supplied (time-sensitive; labelled).")
            except Exception:  # noqa: BLE001 - never break the turn on company context
                company_summary = None
        messages = build_evidence_messages(
            query=query,
            sections=sections,
            tool_summaries=tool_summaries,
            job_description=job_description,
            candidate_background=candidate_background,
            coverage_notes=coverage_notes,
            company_summary=company_summary,
        )
        answer_text, usage = self._synthesize(
            messages, trace, rag_required=rag_required,
            results=results, tool_summaries=tool_summaries, model=model,
            structured_evidence=structured_evidence, coverage_notes=coverage_notes,
        )

        # Output guard: redact secret-like strings, flag leakage / bad citations.
        allowed_markers = {c.marker for c in citations}
        guarded = guard_output(answer_text, allowed_markers=allowed_markers)
        answer_text = guarded.safe_answer
        if guarded.findings:
            trace.output_findings = guarded.findings
            trace.notes.extend(guarded.findings)

        # 10) Citations map to referenced, real evidence (structured or narrative).
        referenced = {f"[{n}]" for n in _MARKER_RE.findall(answer_text)}
        cited = [c for c in citations if c.marker in referenced]

        response = ChatResponse(
            answer=answer_text,
            citations=cited,
            retrieved=results,
            evidence=evidence,
            tool_calls=[te.execution for te in tool_execs],
            translated_query=translated,
            usage=usage,
        )
        return OrchestrationResult(
            response=response, trace=trace,
            preparation_artifacts=tool_outcome.artifacts,
        )

    # -- dry-run planning (OPT-5) ------------------------------------------

    def plan(
        self,
        query: str,
        *,
        job_description: str | None = None,
        candidate_background: str | None = None,
        days_until_interview: int | None = None,
        hours_per_week: float | None = None,
    ) -> PipelinePlan:
        """Preview what ``query`` would trigger, using only deterministic
        heuristics — no query-translation LLM call, no retrieval, no synthesis,
        no tool execution. Safe to call for free before running ``answer``.
        """
        from src.copilot.knowledge.router import detect_country, route_question
        from src.copilot.rag.translation import heuristic_translation

        cleaned = validate_input(query or "", "query").cleaned
        translated = heuristic_translation(cleaned)
        route_decision = route_question(cleaned)
        route = route_for_intent(translated.intent)
        rag_required = route.rag_required and translated.retrieval_required

        # Predict tool execution from the same input-gating rules as _run_tools,
        # without invoking anything.
        planned = list(route.tools)
        expected: list[str] = []
        skipped: list[str] = []
        have_jd = bool(job_description)
        have_bg = bool(candidate_background)
        for tool in planned:
            if tool == constants.TOOL_JOB_ANALYZER:
                (expected if have_jd else skipped).append(tool)
            elif tool == constants.TOOL_GAP_ANALYZER:
                (expected if (have_jd and have_bg) else skipped).append(tool)
            elif tool == constants.TOOL_PREP_PLANNER:
                ready = have_jd and have_bg and days_until_interview and hours_per_week
                (expected if ready else skipped).append(tool)
            elif tool == constants.TOOL_QUESTION_GENERATOR:
                expected.append(tool)  # runs from retrieved context
            else:
                expected.append(tool)

        steps = ["Validate + injection-scan the question"]
        if rag_required:
            steps.append("Hybrid retrieval over the knowledge base")
        if route_decision.lane and route_decision.lane != "vector":
            steps.append(f"Structured retrieval (lane: {route_decision.lane})")
        if expected:
            steps.append("Run tools: " + ", ".join(expected))
        steps.append("Synthesise a grounded, cited answer")

        notes: list[str] = []
        if skipped:
            notes.append("Provide more inputs to enable: " + ", ".join(skipped))
        notes.append("Preview only — heuristic routing; the live run may refine "
                     "the intent with the translation model.")

        return PipelinePlan(
            query=cleaned, intent=translated.intent,
            retrieval_lane=route_decision.lane, lane_reason=route_decision.reason,
            detected_country=detect_country(cleaned), rag_required=rag_required,
            tools_planned=planned, tools_expected_to_run=expected,
            tools_skipped_no_input=skipped, steps=steps, notes=notes,
        )

    # -- retrieval calibration (OPT-1B / OPT-2) ----------------------------

    def _maybe_rerank(self, query, results, trace):
        """Apply the configured reranker (default NoOp) to the RRF candidates."""
        provider = (getattr(self.config, "reranker_provider", "none") or "none").lower()
        top_k = getattr(self.config, "rerank_top_k", self.top_k) or self.top_k
        if provider == "none" or not results:
            trace.reranker_provider = "none"
            return results
        from src.copilot.retrieval.reranker import build_reranker
        candidates = results[: getattr(self.config, "rerank_candidates", len(results))]
        outcome = build_reranker(self.config).rerank(query, candidates, top_k=top_k)
        trace.reranker_used = outcome.reranker_used
        trace.reranker_provider = outcome.reranker_provider
        trace.reranked_count = outcome.reranked_count
        trace.reranker_latency_ms = outcome.reranker_latency_ms
        trace.notes.extend(outcome.notes)
        return outcome.results or results

    def _record_weight_trace(self, query, trace):
        """Record effective hybrid weights + a deterministic dominant-signal label."""
        base_v = getattr(self.config, "hybrid_vector_weight", 1.0) if self.config else 1.0
        base_k = getattr(self.config, "hybrid_keyword_weight", 1.0) if self.config else 1.0
        adaptive = bool(getattr(self.config, "hybrid_adaptive", False))
        if adaptive:
            from src.copilot.retrieval.adaptive import classify_weight_signal
            reason, v, k = classify_weight_signal(query, base_vector=base_v, base_keyword=base_k)
            trace.weight_strategy = "adaptive"
            trace.weight_reason_code = reason
            trace.effective_vector_weight, trace.effective_keyword_weight = v, k
        else:
            trace.weight_strategy = "configured"
            trace.weight_reason_code = "DEFAULT_EQUAL" if base_v == base_k else "CONFIGURED_WEIGHTS"
            trace.effective_vector_weight, trace.effective_keyword_weight = base_v, base_k

    # -- stages ------------------------------------------------------------

    def _sanitize_context(
        self, text: str | None, kind: str, label: str, trace: PipelineTrace
    ) -> str | None:
        """Validate + injection-scan an untrusted structured input.

        A blocked input is dropped (not fed to tools or the model); a flagged one
        is kept with a warning. Returns the cleaned text or ``None``.
        """
        if not text:
            return None
        validation = validate_input(text, kind)
        trace.notes.extend(validation.notes)
        if not validation.ok:
            trace.notes.append(f"{label} rejected: {validation.error}")
            return None
        scan = scan_text(validation.cleaned)
        if scan.blocked:
            trace.degraded.append(f"{kind}_input")
            trace.notes.append(
                f"{label} contained embedded instructions and was ignored for safety."
            )
            return None
        if scan.flagged:
            trace.notes.append(f"{label} flagged (allowed with warning).")
        return validation.cleaned

    def _retrieve(
        self, translated: TranslatedQuery, trace: PipelineTrace
    ) -> list[RetrievalResult]:
        if self.retriever is None:
            from src.copilot.retrieval import build_retriever
            from src.copilot.vectorstore import build_vector_store

            if self.config is None:
                trace.notes.append("No retriever/config available; skipped retrieval.")
                return []
            try:
                store = build_vector_store(self.config)
                self.retriever = build_retriever(self.config, store=store)
            except Exception:  # noqa: BLE001
                trace.degraded.append("retrieval")
                trace.notes.append("Could not build the retriever; skipped retrieval.")
                return []

        filters = translated.metadata_filters or None
        is_hybrid = isinstance(self.retriever, HybridRetriever)

        # Per-query retrieval, fused across the translated queries. For the
        # PRIMARY (rewritten) query on a hybrid retriever we call search() once
        # and reuse its result for BOTH fusion and the RAG Inspector channels —
        # previously a second search() ran on the same query purely for the
        # inspector, duplicating the vector embedding + BM25 lookup. Alternate
        # query variants still trigger their own retrieval.
        per_query: list[list[RetrievalResult]] = []
        for index, query in enumerate(translated.all_queries):
            try:
                if is_hybrid:
                    detail = self.retriever.search(query, top_k=self.top_k, filters=filters)
                    per_query.append(detail.fused)
                    if index == 0:  # primary query → inspector channels (no re-search)
                        trace.retrieval_strategy = "hybrid"
                        trace.vector_results = detail.vector
                        trace.keyword_results = detail.keyword
                        for channel in detail.degraded:
                            if channel not in trace.degraded:
                                trace.degraded.append(channel)
                else:
                    per_query.append(
                        self.retriever.retrieve(query, top_k=self.top_k, filters=filters)
                    )
            except Exception:  # noqa: BLE001 - one query failing must not abort
                trace.degraded.append("retrieval")
                per_query.append([])
        results = reciprocal_rank_fusion(per_query, top_k=self.top_k)

        # Inspector strategy/channels for the non-hybrid retrievers (fused only).
        if not is_hybrid:
            if isinstance(self.retriever, VectorRetriever):
                trace.retrieval_strategy = "vector"
                trace.vector_results = results
            elif isinstance(self.retriever, KeywordRetriever):
                trace.retrieval_strategy = "keyword"
                trace.keyword_results = results

        trace.fused_results = results
        trace.rag_used = bool(results)
        if not results:
            trace.notes.append("No evidence retrieved for this query.")
        return results

    def _run_tools(
        self,
        route,
        trace: PipelineTrace,
        *,
        job_description,
        candidate_background,
        days_until_interview,
        hours_per_week,
        question_focus,
        results,
    ) -> ToolRunOutcome:
        executions: list = []
        summaries: list[str] = []
        role_req = None
        gap_res = None
        prep_plan = None
        question_set = None

        def record(name: str, args: dict):
            result = self.tool_invoker.invoke(name, args)
            executions.append(result)
            trace.tools_invoked.append(name)
            if result.execution.status != "ok":
                trace.notes.append(f"{name}: {result.execution.status}.")
                if result.execution.status == "error":
                    trace.degraded.append(name)
            return result

        for tool in route.tools:
            if tool == constants.TOOL_JOB_ANALYZER:
                if not job_description:
                    trace.notes.append("Job analyzer skipped: no job description provided.")
                    continue
                res = record(tool, {"job_description": job_description})
                if res.ok:
                    role_req = res.result
                    summaries.append(
                        f"Role requirements: {len(role_req.required_skills)} required "
                        f"skills, {len(role_req.technologies)} technologies; role="
                        f"{role_req.role_title or 'n/a'}."
                    )
            elif tool == constants.TOOL_GAP_ANALYZER:
                if not (candidate_background and role_req):
                    trace.notes.append(
                        "Gap analyzer skipped: needs candidate background and role requirements."
                    )
                    continue
                res = record(
                    tool,
                    {
                        "candidate_background": candidate_background,
                        "role_requirements": role_req.model_dump(),
                    },
                )
                if res.ok:
                    gap_res = res.result
                    s = gap_res.stats
                    summaries.append(
                        f"Gap analysis: match {s.match_percentage}% (weighted "
                        f"{s.weighted_match_percentage}%); {s.matched} matched, "
                        f"{s.partial} partial, {s.missing} missing."
                    )
            elif tool == constants.TOOL_PREP_PLANNER:
                if not (gap_res and gap_res.priority_gaps and days_until_interview and hours_per_week):
                    trace.notes.append(
                        "Preparation planner skipped: needs gaps, days and hours."
                    )
                    continue
                res = record(
                    tool,
                    {
                        "priority_gaps": [g.model_dump() for g in gap_res.priority_gaps],
                        "days_until_interview": int(days_until_interview),
                        "hours_per_week": float(hours_per_week),
                    },
                )
                if res.ok:
                    plan = res.result
                    prep_plan = plan
                    summaries.append(
                        f"Preparation plan: {plan.total_available_hours}h over "
                        f"{len(plan.weekly_structure)} week(s)."
                    )
            elif tool == constants.TOOL_QUESTION_GENERATOR:
                role = (role_req.role_title if role_req else None) or ""
                if not role:
                    trace.notes.append("Question generator skipped: no role identified.")
                    continue
                requirements = (
                    (role_req.required_skills + role_req.technologies) if role_req else []
                )
                evidence = [r.text[:200] for r in results[:3]]
                res = record(
                    tool,
                    {
                        "role": role,
                        "requirements": requirements,
                        "evidence": evidence,
                        "focus": question_focus or [],
                    },
                )
                if res.ok:
                    qset = res.result
                    question_set = qset
                    total = sum(len(c.questions) for c in qset.categories)
                    summaries.append(
                        f"Interview questions: {total} across {len(qset.categories)} categories."
                    )

        return ToolRunOutcome(
            executions=executions,
            summaries=summaries,
            artifacts=PreparationArtifacts(
                role_requirements=role_req,
                gap_result=gap_res,
                preparation_plan=prep_plan,
                question_set=question_set,
            ),
        )

    # -- structured retrieval + evidence assembly --------------------------

    def _structured_retrieval(self, route_decision, query, trace):
        """Run the injected structured coordinator; record trace + coverage notes."""
        self._clarify_message = None
        coord = self.knowledge_coordinator
        if coord is None:
            return [], []
        try:
            outcome = coord.retrieve(route_decision, query, country=trace.detected_country)
        except Exception as exc:  # noqa: BLE001 - structured retrieval never crashes
            trace.notes.append(f"Structured retrieval error: {type(exc).__name__}")
            return [], []

        trace.sources_considered = list(outcome.sources_considered)
        trace.source_precedence = list(outcome.source_precedence)
        trace.structured_queries = list(outcome.structured_queries)
        trace.structured_record_count = len(outcome.evidence)
        trace.coverage_notes = list(outcome.notes)
        if outcome.resolved:
            trace.resolved_occupation = outcome.resolved.phrase
            trace.occupation_candidates = [c.title for c in outcome.resolved.candidates]

        if outcome.clarify and outcome.resolved:
            names = ", ".join(c.title for c in outcome.resolved.candidates[:4])
            self._clarify_message = (
                f"Your question could refer to more than one occupation "
                f"({names}). Which one did you mean?"
            )
        return outcome.evidence, list(outcome.notes)

    # Which evidence types belong to which synthesis section.
    _SECTION_OF = {
        "role_task": "structured_role", "skill": "structured_role",
        "knowledge": "structured_role", "activity": "structured_role",
        "technology": "structured_role", "transition": "structured_role",
        "education": "structured_role", "training": "structured_role",
        "certification": "structured_role", "licence": "structured_role",
        "compensation": "compensation",
        "forecast": "labour_market", "openings": "labour_market", "shortage": "labour_market",
        "outlook": "labour_market", "vacancy": "labour_market",
        "competency": "competency", "behaviour": "competency", "qualification": "competency",
        "narrative": "narrative",
    }

    def _assemble_evidence(self, structured_evidence, results):
        """Merge structured + narrative evidence into numbered, sectioned context.

        Structured, higher-authority evidence is ranked ahead of narrative chunks;
        equivalent items are de-duplicated; the whole set is bounded by the context
        budget. Returns ``(evidence, sections, citations)`` with markers [1..N].
        """
        combined: list[KnowledgeEvidence] = list(structured_evidence)
        for i, r in enumerate(results):
            combined.append(KnowledgeEvidence.from_retrieval_result(r, index=i))

        # Rank: structured before narrative, then by score; narrative keeps order.
        def _key(item):
            is_narrative = item.retrieval_lane == "vector"
            return (1 if is_narrative else 0, -item.score)

        combined.sort(key=_key)

        # De-duplicate equivalent evidence (same source + text).
        seen, deduped = set(), []
        for e in combined:
            key = (e.source_id, e.evidence_type, e.text[:120])
            if key in seen:
                continue
            seen.add(key); deduped.append(e)

        # Bound by the context budget.
        evidence, used = [], 0
        for e in deduped:
            if evidence and used + len(e.text) > self.max_context_chars:
                break
            evidence.append(e); used += len(e.text) + 40

        sections: dict[str, list[str]] = {}
        citations: list[Citation] = []
        for idx, e in enumerate(evidence, start=1):
            marker = f"[{idx}]"
            section = self._SECTION_OF.get(e.evidence_type, "narrative")
            sections.setdefault(section, []).append(f"{marker} {e.text}")
            citations.append(e.to_citation(marker))
        return evidence, sections, citations

    def _get_synthesis_responder(self, model: str | None) -> Responder:
        if self._synthesis_responder is not None:
            return self._synthesis_responder
        from src.copilot.rag.responder import build_openrouter_responder

        # Reasoning models (gpt-5*) spend tokens on reasoning before emitting the
        # answer; the default 1024 cap can be exhausted before any content is
        # produced (empty reply → blank chat). Give synthesis explicit headroom.
        return build_openrouter_responder(
            self.config,
            model=model,
            max_tokens=constants.SYNTHESIS_MAX_OUTPUT_TOKENS,
        )

    def _synthesize(
        self, messages, trace, *, rag_required, results, tool_summaries, model,
        structured_evidence=None, coverage_notes=None,
    ):
        structured_evidence = structured_evidence or []
        coverage_notes = coverage_notes or []
        try:
            responder = self._get_synthesis_responder(model)
            reply = responder(messages)
            content = (reply.content or "").strip()
            if not content:
                # A reasoning model can hit the token cap during reasoning and
                # return empty content (finish_reason=length). Never show a blank
                # chat bubble — fall back to a visible summary of what we have.
                trace.degraded.append("model")
                trace.notes.append(
                    "The model returned no answer text (likely truncated by the "
                    "output-token limit); returned a limited summary instead."
                )
                return self._fallback_answer(
                    rag_required, results, tool_summaries, structured_evidence, coverage_notes
                ), reply.usage
            return content, reply.usage
        except Exception:  # noqa: BLE001 - model/config failure must not crash
            trace.degraded.append("model")
            trace.notes.append("The model was unavailable; returned a limited summary.")
            return self._fallback_answer(
                rag_required, results, tool_summaries, structured_evidence, coverage_notes
            ), None

    @staticmethod
    def _fallback_answer(rag_required, results, tool_summaries,
                         structured_evidence=None, coverage_notes=None) -> str:
        parts = ["The assistant model is currently unavailable, so this is a limited summary."]
        if tool_summaries:
            parts.append("Tool results (calculated): " + " ".join(tool_summaries))
        for i, e in enumerate(structured_evidence or [], start=1):
            parts.append(f"[{i}] {e.text}")
        if results:
            parts.append(f"Retrieved {len(results)} narrative passage(s) — see sources.")
        elif rag_required and not structured_evidence:
            parts.append(constants.INSUFFICIENT_EVIDENCE_MESSAGE)
        for note in coverage_notes or []:
            parts.append(note)
        return " ".join(parts)

    def _plain_result(self, message: str, trace: PipelineTrace) -> OrchestrationResult:
        return OrchestrationResult(
            response=ChatResponse(answer=message), trace=trace
        )
