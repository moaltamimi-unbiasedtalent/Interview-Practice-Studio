"""Deterministic hybrid weight signals (OPT-2A) — EXPERIMENTAL, off by default.

Classifies a query into a keyword-heavy / semantic-heavy / neutral bucket using
only observable surface features (never model reasoning) and returns a reason code
plus suggested weights. Enabling adaptive weighting is gated by config and should
be justified by evaluation; by default the router records DEFAULT_EQUAL and leaves
the configured weights unchanged.
"""

from __future__ import annotations

import re

__all__ = ["classify_weight_signal", "dominant_signal"]

_ACRONYM = re.compile(r"\b([A-Z]{2,5}|[A-Z]{2,4}\d{2,4})\b")            # PMP, ISO 27001, CISSP
_CODE = re.compile(r"\b(\d{2}-\d{4}|[A-Z]{1,3}-?\d{2,4}|iso\s?\d{3,5})\b", re.I)
_QUOTED = re.compile(r'"[^"]{2,}"')
_TECH = re.compile(r"\b(python|java|sql|aws|azure|excel|sap|kubernetes|tableau|c\+\+|react)\b", re.I)
_CONCEPTUAL = re.compile(r"\b(why|how|what makes|explain|describe|difference between|approach|strategy)\b", re.I)


def classify_weight_signal(query: str, *, base_vector: float, base_keyword: float
                           ) -> tuple[str, float, float]:
    """Return ``(reason_code, vector_weight, keyword_weight)``.

    Reason codes are simple deterministic labels (EXACT_TOKEN_HEAVY /
    CONCEPTUAL_QUERY / DEFAULT_EQUAL), never chain-of-thought.
    """
    q = query or ""
    keyword_hits = bool(_ACRONYM.search(q) or _CODE.search(q) or _QUOTED.search(q)
                        or _TECH.search(q))
    conceptual = bool(_CONCEPTUAL.search(q)) or len(q.split()) >= 14
    if keyword_hits and not conceptual:
        return "EXACT_TOKEN_HEAVY", base_vector * 0.6, base_keyword * 1.6
    if conceptual and not keyword_hits:
        return "CONCEPTUAL_QUERY", base_vector * 1.6, base_keyword * 0.6
    return "DEFAULT_EQUAL", base_vector, base_keyword


def dominant_signal(vector_results, keyword_results, fused_results) -> str:
    """A short, observable summary of which channel drove the top fused result.

    Derived from ranks/ids only — not from model reasoning.
    """
    if not fused_results:
        return "No retrieval signal (empty result set)."
    top_id = getattr(fused_results[0].chunk, "chunk_id", None)
    kw_ids = [getattr(r.chunk, "chunk_id", None) for r in (keyword_results or [])[:3]]
    vec_ids = [getattr(r.chunk, "chunk_id", None) for r in (vector_results or [])[:3]]
    in_kw, in_vec = top_id in kw_ids, top_id in vec_ids
    if in_kw and not in_vec:
        return "Dominant retrieval signal: keyword — exact skill/certification tokens."
    if in_vec and not in_kw:
        return "Dominant retrieval signal: vector — conceptual semantic match."
    if in_kw and in_vec:
        return "Dominant retrieval signal: both channels agree on the top result."
    return "Dominant retrieval signal: fused ranking (no single channel dominates)."
