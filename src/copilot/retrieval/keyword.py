"""Lexical (BM25) retrieval over the career knowledge base.

BM25 excels at *exact* term matching — technologies, tools, certifications and
job titles (``Python``, ``SAP``, ``ISO 27001``, ``CIPD``, ``SHRM``, ``SQL``) —
where a semantic embedder can drift to merely related concepts. It indexes the
same chunks as the vector store and preserves their metadata, returning the same
:class:`RetrievalResult` type so it is interchangeable with vector retrieval.
"""

from __future__ import annotations

import re

from src.copilot import constants
from src.copilot.models import DocumentChunk, RetrievalResult

__all__ = ["KeywordRetriever", "tokenize"]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lower-case alphanumeric tokenisation shared by index and query.

    ``"ISO 27001"`` -> ``["iso", "27001"]``; ``"SQL"`` -> ``["sql"]``. Using the
    same tokeniser for documents and queries is what makes exact-term matching
    reliable.
    """
    return _TOKEN_RE.findall(text.lower())


def _matches(metadata: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    return all(metadata.get(key) == value for key, value in filters.items())


class KeywordRetriever:
    """BM25 retrieval over a fixed corpus of chunks."""

    def __init__(self, chunks: list[DocumentChunk]) -> None:
        self._chunks = list(chunks)
        self._bm25 = None
        if self._chunks:
            try:
                from rank_bm25 import BM25Okapi  # optional dependency ([rag] extra)
            except ImportError:
                # Degrade gracefully: no BM25 -> empty keyword results, so hybrid
                # falls back to vector-only rather than crashing.
                return
            corpus = [tokenize(chunk.text) for chunk in self._chunks]
            # Guard against a corpus of only empty token lists (BM25 divides by
            # the average document length).
            if any(corpus):
                self._bm25 = BM25Okapi(corpus)

    @classmethod
    def from_store(cls, store) -> "KeywordRetriever":
        """Build a BM25 index from the same chunks held by a vector store."""
        return cls(store.all_chunks())

    def count(self) -> int:
        return len(self._chunks)

    def retrieve(
        self,
        query: str,
        top_k: int = constants.DEFAULT_TOP_K,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        """Return up to ``top_k`` chunks ranked by BM25 score (score > 0)."""
        query = (query or "").strip()
        if not query or self._bm25 is None or top_k <= 0:
            return []
        query_tokens = tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        scored: list[RetrievalResult] = []
        for chunk, score in zip(self._chunks, scores):
            score = float(score)
            if score <= 0.0:
                continue  # no lexical overlap
            if not _matches(chunk.metadata, filters):
                continue
            scored.append(
                RetrievalResult(chunk=chunk, score=score, retriever="keyword")
            )
        scored.sort(key=lambda result: result.score, reverse=True)
        return scored[:top_k]
