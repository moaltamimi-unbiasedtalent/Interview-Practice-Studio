"""A simple, honest retrieval comparison baseline for the three modes.

Without human relevance labels we cannot measure true relevance, and we must not
pretend to. This baseline reports **lexical proxy metrics** on probes whose
``expected_terms`` are exact strings a relevant chunk should contain (e.g. the
query ``"ISO 27001 controls"`` expects a chunk containing ``"ISO 27001"``):

* ``term_recall@k`` — fraction of probes where some top-k chunk contains an
  expected term (a lexical signal, not semantic relevance);
* ``coverage`` — fraction of probes returning at least one result;
* ``avg_results`` — mean number of results returned.

These characterise behaviour on exact-term probes; they do **not** by themselves
prove one mode is better overall — see ``docs/hybrid_search.md``.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from src.copilot import constants

__all__ = ["RetrievalProbe", "ModeMetrics", "evaluate_modes", "load_probes"]


@dataclass
class RetrievalProbe:
    """One evaluation probe: a query and the exact terms a hit should contain."""

    query: str
    expected_terms: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class ModeMetrics:
    """Aggregated proxy metrics for one retrieval mode."""

    mode: str
    probes: int
    term_recall_at_k: float
    coverage: float
    avg_results: float

    def as_dict(self) -> dict:
        return asdict(self)


def _term_hit(results, expected_terms: list[str]) -> bool:
    if not expected_terms:
        return False
    haystacks = [r.chunk.text.lower() for r in results]
    return any(
        term.lower() in haystack for term in expected_terms for haystack in haystacks
    )


def evaluate_modes(
    retrievers: dict[str, object],
    probes: list[RetrievalProbe],
    *,
    top_k: int = constants.DEFAULT_TOP_K,
) -> dict[str, ModeMetrics]:
    """Compute proxy metrics for each named retriever over the probes."""
    metrics: dict[str, ModeMetrics] = {}
    total = len(probes)
    for mode, retriever in retrievers.items():
        term_hits = 0
        covered = 0
        result_counts = 0
        for probe in probes:
            results = retriever.retrieve(probe.query, top_k=top_k)
            result_counts += len(results)
            if results:
                covered += 1
            if _term_hit(results, probe.expected_terms):
                term_hits += 1
        metrics[mode] = ModeMetrics(
            mode=mode,
            probes=total,
            term_recall_at_k=(term_hits / total) if total else 0.0,
            coverage=(covered / total) if total else 0.0,
            avg_results=(result_counts / total) if total else 0.0,
        )
    return metrics


def load_probes(path: str) -> list[RetrievalProbe]:
    """Load probes from a JSON file with a top-level ``probes`` array."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    probes = data.get("probes", data) if isinstance(data, dict) else data
    return [
        RetrievalProbe(
            query=item["query"],
            expected_terms=item.get("expected_terms", []),
            note=item.get("note"),
        )
        for item in probes
    ]
