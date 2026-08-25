"""Reciprocal Rank Fusion (RRF) for merging multiple ranked result lists.

When query translation produces several retrieval queries, each returns its own
ranked list. RRF merges them deterministically: a chunk's fused score is the sum
over lists of ``1 / (k + rank)``. This rewards chunks that rank highly across
queries without depending on raw, incomparable similarity scores — and it never
just concatenates the lists.
"""

from __future__ import annotations

from src.copilot import constants
from src.copilot.models import RetrievalResult

__all__ = ["reciprocal_rank_fusion"]


def reciprocal_rank_fusion(
    ranked_lists: list[list[RetrievalResult]],
    *,
    k: int = constants.RRF_K,
    top_k: int | None = None,
    weights: list[float] | None = None,
    retriever_label: str = "fusion",
) -> list[RetrievalResult]:
    """Fuse ranked result lists into one deduplicated, re-ranked list.

    Duplicate chunks (same ``chunk_id``) are merged; the fused score is the
    (optionally weighted) RRF sum across lists: ``Σ weightᵢ / (k + rankᵢ)``. Ties
    break deterministically by chunk id so results are reproducible. The returned
    :class:`RetrievalResult`s carry the fused score and ``retriever_label``.

    ``weights`` (one per list) makes the channel weighting explicit and
    configurable — equal weights by default, so no channel is favoured without
    evidence.
    """
    if weights is not None and len(weights) != len(ranked_lists):
        raise ValueError("weights must have one entry per ranked list")

    fused_scores: dict[str, float] = {}
    best_result: dict[str, RetrievalResult] = {}

    for list_index, results in enumerate(ranked_lists):
        weight = 1.0 if weights is None else weights[list_index]
        for rank, result in enumerate(results):
            chunk_id = result.chunk.chunk_id
            fused_scores[chunk_id] = (
                fused_scores.get(chunk_id, 0.0) + weight / (k + rank + 1)
            )
            # Keep the instance with the highest original score for its content.
            if chunk_id not in best_result or result.score > best_result[chunk_id].score:
                best_result[chunk_id] = result

    ordered = sorted(
        fused_scores.items(),
        key=lambda item: (-item[1], item[0]),  # score desc, then id asc (stable)
    )

    fused: list[RetrievalResult] = []
    for chunk_id, score in ordered:
        source = best_result[chunk_id]
        fused.append(
            RetrievalResult(chunk=source.chunk, score=score, retriever=retriever_label)
        )
    if top_k is not None:
        fused = fused[:top_k]
    return fused
