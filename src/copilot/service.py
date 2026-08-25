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
from src.copilot.config import CopilotConfig
from src.copilot.models import ChatResponse, RetrievalResult, ToolExecution, TranslatedQuery
from src.copilot.rag.context import build_context
from src.copilot.rag.responder import Responder
from src.copilot.rag.routing import route_for_intent
from src.copilot.rag.synthesis import build_synthesis_messages
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
    # RAG metrics (safe; counts + latency only).
    retrieval_strategy: str = ""
    translated_query_count: int = 0
    context_count: int = 0
    retrieval_latency_ms: float = 0.0
    # Security.
    input_verdict: str = "allow"
    input_indicators: list[str] = field(default_factory=list)
    blocked: bool = False
    excluded_chunks: int = 0
    output_findings: list[str] = field(default_factory=list)


@dataclass
class OrchestrationResult:
    """The service's result: a grounded response plus the pipeline trace."""

    response: ChatResponse
    trace: PipelineTrace

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
        top_k: int = constants.DEFAULT_TOP_K,
        max_context_chars: int = constants.MAX_CONTEXT_CHARS,
    ) -> None:
        self.config = config
        self.retriever = retriever
        self.translator = translator or QueryTranslator(config=config)
        self.tool_invoker = tool_invoker or ToolInvoker(build_tool_registry(config=config))
        self._synthesis_responder = synthesis_responder
        self.top_k = top_k
        self.max_context_chars = max_context_chars

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

        # 2) Intent understanding + 3) query translation (fallback built in).
        _step("Translating query")
        translated = self.translator.translate(query)
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

        trace.context_count = len(results)
        bundle = build_context(results, max_chars=self.max_context_chars)
        trace.evidence_sources = [c.label for c in bundle.citations]

        # 6) Tool requirement + 7) tool execution (controlled).
        if route.tools:
            _step("Running tools")
        tool_execs, tool_summaries = self._run_tools(
            route,
            trace,
            job_description=job_description,
            candidate_background=candidate_background,
            days_until_interview=days_until_interview,
            hours_per_week=hours_per_week,
            question_focus=question_focus,
            results=results,
        )

        # 8) Bounded, trust-separated context + 9) OpenRouter synthesis.
        _step("Preparing response")
        messages = build_synthesis_messages(
            query=query,
            evidence_context=bundle.context_text,
            tool_summaries=tool_summaries,
            job_description=job_description,
            candidate_background=candidate_background,
        )
        answer_text, usage = self._synthesize(
            messages, trace, rag_required=rag_required,
            results=results, tool_summaries=tool_summaries, model=model,
        )

        # Output guard: redact secret-like strings, flag leakage / bad citations.
        allowed_markers = {c.marker for c in bundle.citations}
        guarded = guard_output(answer_text, allowed_markers=allowed_markers)
        answer_text = guarded.safe_answer
        if guarded.findings:
            trace.output_findings = guarded.findings
            trace.notes.extend(guarded.findings)

        # 10) Citations map to referenced, real retrieved chunks.
        referenced = {f"[{n}]" for n in _MARKER_RE.findall(answer_text)}
        citations = [c for c in bundle.citations if c.marker in referenced]

        response = ChatResponse(
            answer=answer_text,
            citations=citations,
            retrieved=results,
            tool_calls=[te.execution for te in tool_execs],
            translated_query=translated,
            usage=usage,
        )
        return OrchestrationResult(response=response, trace=trace)

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

        # Per-query retrieval, fused across the translated queries.
        per_query: list[list[RetrievalResult]] = []
        for query in translated.all_queries:
            try:
                per_query.append(
                    self.retriever.retrieve(query, top_k=self.top_k, filters=filters)
                )
            except Exception:  # noqa: BLE001 - one query failing must not abort
                trace.degraded.append("retrieval")
                per_query.append([])
        results = reciprocal_rank_fusion(per_query, top_k=self.top_k)

        # Channel detail for the inspector (best-effort).
        try:
            if isinstance(self.retriever, HybridRetriever):
                trace.retrieval_strategy = "hybrid"
                detail = self.retriever.search(
                    translated.rewritten_query, top_k=self.top_k, filters=filters
                )
                trace.vector_results = detail.vector
                trace.keyword_results = detail.keyword
                for channel in detail.degraded:
                    if channel not in trace.degraded:
                        trace.degraded.append(channel)
            elif isinstance(self.retriever, VectorRetriever):
                trace.retrieval_strategy = "vector"
                trace.vector_results = results
            elif isinstance(self.retriever, KeywordRetriever):
                trace.retrieval_strategy = "keyword"
                trace.keyword_results = results
        except Exception:  # noqa: BLE001 - inspector detail is non-critical
            pass

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
    ) -> tuple[list, list[str]]:
        executions: list = []
        summaries: list[str] = []
        role_req = None
        gap_res = None

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
                    total = sum(len(c.questions) for c in qset.categories)
                    summaries.append(
                        f"Interview questions: {total} across {len(qset.categories)} categories."
                    )

        return executions, summaries

    def _get_synthesis_responder(self, model: str | None) -> Responder:
        if self._synthesis_responder is not None:
            return self._synthesis_responder
        from src.copilot.rag.responder import build_openrouter_responder

        return build_openrouter_responder(self.config, model=model)

    def _synthesize(
        self, messages, trace, *, rag_required, results, tool_summaries, model
    ):
        try:
            responder = self._get_synthesis_responder(model)
            reply = responder(messages)
            return reply.content, reply.usage
        except Exception:  # noqa: BLE001 - model/config failure must not crash
            trace.degraded.append("model")
            trace.notes.append("The model was unavailable; returned a limited summary.")
            return self._fallback_answer(rag_required, results, tool_summaries), None

    @staticmethod
    def _fallback_answer(rag_required, results, tool_summaries) -> str:
        parts = ["The assistant model is currently unavailable, so this is a limited summary."]
        if tool_summaries:
            parts.append("Tool results (calculated): " + " ".join(tool_summaries))
        if results:
            parts.append(f"Retrieved {len(results)} evidence passage(s) — see sources.")
        elif rag_required:
            parts.append(constants.INSUFFICIENT_EVIDENCE_MESSAGE)
        return " ".join(parts)

    def _plain_result(self, message: str, trace: PipelineTrace) -> OrchestrationResult:
        return OrchestrationResult(
            response=ChatResponse(answer=message), trace=trace
        )
