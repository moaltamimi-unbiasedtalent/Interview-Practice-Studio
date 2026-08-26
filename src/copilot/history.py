"""Career conversation history, per-turn RAG metrics, usage and export.

Everything here is *safe* structured data — no prompts, no secrets, no raw
retrieved text beyond short citation labels. History and the usage ledger live in
Streamlit session state (no database).
"""

from __future__ import annotations

import csv
import io
import json

from pydantic import BaseModel, ConfigDict, Field

from src.core.usage import Operation, UsageLedger, UsageRecord

__all__ = [
    "RagTurnMetrics",
    "CareerTurn",
    "CareerHistory",
    "build_turn",
    "HISTORY_KEY",
    "LEDGER_KEY",
    "get_history",
    "append_turn",
    "clear_history",
    "get_ledger",
    "record_final_generation",
]

HISTORY_KEY = "career.history"
LEDGER_KEY = "career.usage_ledger"


class RagTurnMetrics(BaseModel):
    """Safe retrieval metrics for one Career turn (counts + latency only)."""

    retrieval_strategy: str = ""
    translated_query_count: int = 0
    vector_count: int = 0
    keyword_count: int = 0
    fused_count: int = 0
    context_count: int = 0
    retrieval_latency_ms: float = 0.0


class CareerTurn(BaseModel):
    """One question/answer turn with citations, tools used and RAG metadata."""

    model_config = ConfigDict(str_strip_whitespace=True)

    question: str
    answer: str
    citations: list[dict] = Field(default_factory=list)
    tools: list[dict] = Field(default_factory=list)
    rag: RagTurnMetrics | None = None


class CareerHistory(BaseModel):
    turns: list[CareerTurn] = Field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.model_dump(), indent=2, ensure_ascii=False)

    def to_csv(self) -> str:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["question", "answer", "citations", "tools", "strategy", "context_count", "latency_ms"]
        )
        for turn in self.turns:
            writer.writerow(
                [
                    turn.question,
                    turn.answer,
                    " | ".join(c.get("label", "") for c in turn.citations),
                    " | ".join(
                        f"{t.get('tool_name')}:{t.get('status')}" for t in turn.tools
                    ),
                    turn.rag.retrieval_strategy if turn.rag else "",
                    turn.rag.context_count if turn.rag else 0,
                    turn.rag.retrieval_latency_ms if turn.rag else 0.0,
                ]
            )
        return buffer.getvalue()


def _citation_dicts(citations) -> list[dict]:
    out = []
    for c in citations or []:
        out.append(
            {
                "marker": getattr(c, "marker", None),
                "label": getattr(c, "label", None),
                "title": getattr(c, "title", None),
                "source": getattr(c, "source", None),
                "page": getattr(c, "page", None),
            }
        )
    return out


def _tool_dicts(tool_calls) -> list[dict]:
    out = []
    for t in tool_calls or []:
        out.append(
            {
                "tool_name": getattr(t, "tool_name", None),
                "status": getattr(t, "status", None),
                "duration_seconds": getattr(t, "duration_seconds", None),
                "result_summary": getattr(t, "safe_result_summary", None),
            }
        )
    return out


def build_turn(question: str, result) -> CareerTurn:
    """Build a safe :class:`CareerTurn` from an OrchestrationResult (duck-typed)."""
    trace = getattr(result, "trace", None)
    rag = None
    if trace is not None:
        rag = RagTurnMetrics(
            retrieval_strategy=getattr(trace, "retrieval_strategy", ""),
            translated_query_count=getattr(trace, "translated_query_count", 0),
            vector_count=len(getattr(trace, "vector_results", []) or []),
            keyword_count=len(getattr(trace, "keyword_results", []) or []),
            fused_count=len(getattr(trace, "fused_results", []) or []),
            context_count=getattr(trace, "context_count", 0),
            retrieval_latency_ms=getattr(trace, "retrieval_latency_ms", 0.0),
        )
    return CareerTurn(
        question=question,
        answer=getattr(result, "answer", ""),
        citations=_citation_dicts(getattr(result, "citations", [])),
        tools=_tool_dicts(getattr(result, "tool_calls", [])),
        rag=rag,
    )


# --- Session state helpers ---------------------------------------------------


def get_history(session_state) -> CareerHistory:
    history = session_state.get(HISTORY_KEY)
    if not isinstance(history, CareerHistory):
        history = CareerHistory()
        session_state[HISTORY_KEY] = history
    return history


def append_turn(session_state, turn: CareerTurn) -> None:
    get_history(session_state).turns.append(turn)


def clear_history(session_state) -> None:
    session_state.pop(HISTORY_KEY, None)
    session_state.pop(LEDGER_KEY, None)


def get_ledger(session_state) -> UsageLedger:
    ledger = session_state.get(LEDGER_KEY)
    if not isinstance(ledger, UsageLedger):
        ledger = UsageLedger()
        session_state[LEDGER_KEY] = ledger
    return ledger


def record_final_generation(session_state, usage) -> None:
    """Record a Career final-generation usage record, if token usage is present.

    Cost is left unknown (our LangChain→OpenRouter path does not surface a
    provider cost), so the UI shows 'Cost unavailable' rather than a fabricated
    estimate.
    """
    if usage is None:
        return
    get_ledger(session_state).add(
        UsageRecord(
            operation=Operation.CAREER_FINAL_GENERATION,
            model=getattr(usage, "model", ""),
            prompt_tokens=getattr(usage, "prompt_tokens", 0),
            completion_tokens=getattr(usage, "completion_tokens", 0),
            total_tokens=getattr(usage, "total_tokens", 0),
            cost_usd=getattr(usage, "cost_usd", None),
        )
    )
