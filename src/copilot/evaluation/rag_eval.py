"""Deterministic RAG evaluation for Career Intelligence.

Implements the metric maths (Hit Rate@K, MRR, Recall@K, term-recall), plus
evaluators for the three retrieval strategies, a query-translation comparison,
tool-selection accuracy and citation correctness. All maths is pure and unit-
tested; retrieval runs against a store built from the committed eval corpus.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field

from src.copilot.rag.context import build_context
from src.copilot.rag.routing import route_for_intent
from src.copilot.rag.translation import heuristic_translation
from src.copilot.retrieval.fusion import reciprocal_rank_fusion

__all__ = [
    "RagCase",
    "RetrievalMetrics",
    "hit_rate_at_k",
    "reciprocal_rank",
    "recall_at_k",
    "load_dataset",
    "evaluate_retrieval",
    "evaluate_translation",
    "ToolCase",
    "evaluate_tool_selection",
    "evaluate_citations",
    "grounding_metrics",
]


# --- Dataset -----------------------------------------------------------------


@dataclass
class RagCase:
    id: str
    question: str
    category: str
    expected_sources: list[str] = field(default_factory=list)
    expected_terms: list[str] = field(default_factory=list)


def load_dataset(path: str) -> tuple[list[RagCase], int]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    cases = [
        RagCase(
            id=c["id"],
            question=c["question"],
            category=c.get("category", "uncategorised"),
            expected_sources=c.get("expected_sources", []),
            expected_terms=c.get("expected_terms", []),
        )
        for c in data.get("cases", [])
    ]
    return cases, int(data.get("top_k", 5))


# --- Metric maths (pure) -----------------------------------------------------


def hit_rate_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """1.0 if any relevant source appears in the top-k, else 0.0."""
    return 1.0 if set(ranked[:k]) & relevant else 0.0


def reciprocal_rank(ranked: list[str], relevant: set[str], k: int) -> float:
    """1/rank of the first relevant source within the top-k, else 0.0."""
    for index, source in enumerate(ranked[:k], start=1):
        if source in relevant:
            return 1.0 / index
    return 0.0


def recall_at_k(ranked: list[str], relevant: set[str], k: int) -> float:
    """Fraction of relevant sources present in the top-k."""
    if not relevant:
        return 0.0
    return len(set(ranked[:k]) & relevant) / len(relevant)


# --- Retrieval evaluation ----------------------------------------------------


@dataclass
class RetrievalMetrics:
    mode: str
    cases: int
    hit_rate_at_k: float
    mrr: float
    recall_at_k: float
    term_recall_at_k: float
    avg_latency_ms: float

    def as_dict(self) -> dict:
        return asdict(self)


def _ranked_sources(results) -> list[str]:
    return [(r.metadata or {}).get("filename") or (r.source or "") for r in results]


def _term_hit(results, terms: list[str]) -> bool:
    if not terms:
        return False
    hay = " ".join((r.chunk.text or "").lower() for r in results)
    return any(t.lower() in hay for t in terms)


def _evaluate_one(retrieve, cases: list[RagCase], top_k: int, mode: str) -> RetrievalMetrics:
    hits = rr = rec = term = latency = 0.0
    for case in cases:
        started = time.perf_counter()
        results = retrieve(case.question)
        latency += (time.perf_counter() - started) * 1000.0
        ranked = _ranked_sources(results)
        relevant = set(case.expected_sources)
        hits += hit_rate_at_k(ranked, relevant, top_k)
        rr += reciprocal_rank(ranked, relevant, top_k)
        rec += recall_at_k(ranked, relevant, top_k)
        term += 1.0 if _term_hit(results[:top_k], case.expected_terms) else 0.0
    n = len(cases) or 1
    return RetrievalMetrics(
        mode=mode,
        cases=len(cases),
        hit_rate_at_k=round(hits / n, 3),
        mrr=round(rr / n, 3),
        recall_at_k=round(rec / n, 3),
        term_recall_at_k=round(term / n, 3),
        avg_latency_ms=round(latency / n, 3),
    )


def evaluate_retrieval(retrievers: dict, cases: list[RagCase], top_k: int) -> dict:
    """Evaluate each named retriever over the dataset."""
    return {
        mode: _evaluate_one(
            lambda q, r=retriever: r.retrieve(q, top_k=top_k), cases, top_k, mode
        )
        for mode, retriever in retrievers.items()
    }


# --- Query-translation experiment --------------------------------------------


def evaluate_translation(retriever, translator, cases: list[RagCase], top_k: int) -> dict:
    """Compare original-query vs translated/multi-query retrieval (same cases)."""

    def original(q):
        return retriever.retrieve(q, top_k=top_k)

    def translated(q):
        tq = translator.translate(q)
        ranked_lists = [retriever.retrieve(sub, top_k=top_k) for sub in tq.all_queries]
        return reciprocal_rank_fusion(ranked_lists, top_k=top_k)

    return {
        "original": _evaluate_one(original, cases, top_k, "original"),
        "translated": _evaluate_one(translated, cases, top_k, "translated"),
    }


# --- Tool-selection evaluation -----------------------------------------------


@dataclass
class ToolCase:
    id: str
    query: str
    available_inputs: list[str]
    expected_tools: list[str]


# Inputs each tool needs before it can run (mirrors the service's guards).
_TOOL_REQUIREMENTS = {
    "job_description_analyzer": {"job_description"},
    "candidate_gap_analyzer": {"job_description", "candidate_background"},
    "preparation_plan_calculator": {
        "job_description", "candidate_background", "days", "hours"
    },
    "interview_question_generator": {"role_or_job_description"},
}


def _select_tools(query: str, available: set[str]) -> list[str]:
    """Deterministic selection: heuristic intent → route → filter by inputs."""
    intent = heuristic_translation(query).intent
    planned = route_for_intent(intent).tools
    selected = []
    for tool in planned:
        needs = _TOOL_REQUIREMENTS.get(tool, set())
        if tool == "interview_question_generator":
            if {"role", "job_description"} & available:
                selected.append(tool)
        elif needs <= available:
            selected.append(tool)
    return selected


def evaluate_tool_selection(cases: list[ToolCase]) -> dict:
    """Return accuracy + per-case detail for tool selection."""
    correct = 0
    details = []
    for case in cases:
        selected = _select_tools(case.query, set(case.available_inputs))
        ok = set(selected) == set(case.expected_tools)
        correct += 1 if ok else 0
        details.append(
            {"id": case.id, "expected": case.expected_tools, "selected": selected, "correct": ok}
        )
    total = len(cases) or 1
    return {"accuracy": round(correct / total, 3), "correct": correct, "total": len(cases), "details": details}


# --- Citation correctness ----------------------------------------------------


def evaluate_citations(retriever, cases: list[RagCase], top_k: int) -> dict:
    """Validate that built citations map to retrieved chunks with real sources."""
    valid_mapping = 0
    source_exists = 0
    considered = 0
    for case in cases:
        results = retriever.retrieve(case.question, top_k=top_k)
        if not results:
            continue
        considered += 1
        bundle = build_context(results)
        chunk_ids = {r.chunk.chunk_id for r in results}
        if all(c.chunk_id in chunk_ids for c in bundle.citations):
            valid_mapping += 1
        if all((c.source or c.title) for c in bundle.citations):
            source_exists += 1
    n = considered or 1
    return {
        "cases_considered": considered,
        "valid_id_mapping_rate": round(valid_mapping / n, 3),
        "source_exists_rate": round(source_exists / n, 3),
    }


# --- Optional lightweight grounding ------------------------------------------


def grounding_metrics(answer: str, citations) -> dict:
    """Heuristic grounding: citation coverage + unsupported-claim proxy."""
    import re

    sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer or "") if s.strip()]
    cited = [s for s in sentences if re.search(r"\[\d+\]", s)]
    coverage = round(len(cited) / len(sentences), 3) if sentences else 0.0
    return {
        "sentences": len(sentences),
        "cited_sentences": len(cited),
        "citation_coverage": coverage,
        "distinct_citations": len({getattr(c, "marker", c) for c in (citations or [])}),
    }
