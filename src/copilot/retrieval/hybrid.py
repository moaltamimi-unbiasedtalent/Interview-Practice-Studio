"""Hybrid retrieval: semantic (vector) + lexical (BM25), fused with RRF.

```
query
 ├─ vector search   (semantic / conceptual)
 └─ BM25 search     (exact terms, acronyms, job titles)
        ↓
  reciprocal-rank fusion   (explainable, weight-configurable)
        ↓
  deduplicate + top-k
```

Vector retrieval is retained in full; hybrid only *adds* a lexical channel and
fuses the two. Reciprocal Rank Fusion is used instead of blending raw scores
because vector cosine similarities and BM25 scores are on different, incomparable
scales — RRF combines *ranks*, which is explainable and needs no score
normalisation. Weights are configurable but default to equal, so no channel is
favoured without evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.copilot import constants
from src.copilot.models import RetrievalResult
from src.copilot.retrieval.fusion import reciprocal_rank_fusion
from src.copilot.retrieval.keyword import KeywordRetriever
from src.copilot.retrieval.vector import VectorRetriever

__all__ = ["HybridRetriever", "HybridSearch"]


@dataclass
class HybridSearch:
    """The full detail of one hybrid query, for the RAG Inspector."""

    query: str
    vector: list[RetrievalResult]
    keyword: list[RetrievalResult]
    fused: list[RetrievalResult]


class HybridRetriever:
    """Combine vector and BM25 retrieval with weighted reciprocal-rank fusion."""

    def __init__(
        self,
        vector: VectorRetriever,
        keyword: KeywordRetriever,
        *,
        vector_weight: float = constants.HYBRID_VECTOR_WEIGHT,
        keyword_weight: float = constants.HYBRID_KEYWORD_WEIGHT,
        candidate_k: int = constants.HYBRID_CANDIDATE_K,
    ) -> None:
        self.vector = vector
        self.keyword = keyword
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.candidate_k = candidate_k

    def search(
        self,
        query: str,
        top_k: int = constants.DEFAULT_TOP_K,
        filters: dict | None = None,
    ) -> HybridSearch:
        """Run both channels and fuse them, exposing every stage for inspection."""
        candidate_k = max(top_k, self.candidate_k)
        vector_hits = self.vector.retrieve(query, top_k=candidate_k, filters=filters)
        keyword_hits = self.keyword.retrieve(query, top_k=candidate_k, filters=filters)
        fused = reciprocal_rank_fusion(
            [vector_hits, keyword_hits],
            weights=[self.vector_weight, self.keyword_weight],
            top_k=top_k,
            retriever_label="hybrid",
        )
        return HybridSearch(
            query=query, vector=vector_hits, keyword=keyword_hits, fused=fused
        )

    def retrieve(
        self,
        query: str,
        top_k: int = constants.DEFAULT_TOP_K,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        """Return the fused top-k (interchangeable with the other retrievers)."""
        return self.search(query, top_k=top_k, filters=filters).fused
