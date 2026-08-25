"""Vector retrieval: turn a query into ranked :class:`RetrievalResult`s.

Thin layer over a :class:`~src.copilot.vectorstore.BaseVectorStore`: it embeds
the query (via the store's embedder), asks the store for the nearest chunks, and
maps each raw hit back into a typed ``RetrievalResult`` carrying the chunk text,
score and provenance (source, page, title, metadata).
"""

from __future__ import annotations

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.models import DocumentChunk, RetrievalResult
from src.copilot.vectorstore import BaseVectorStore, VectorHit, build_vector_store

__all__ = ["VectorRetriever", "retrieve"]


def _hit_to_result(hit: VectorHit) -> RetrievalResult:
    metadata = dict(hit.metadata)
    position = metadata.get("chunk_index", 0)
    try:
        position = int(position)
    except (TypeError, ValueError):
        position = 0
    chunk = DocumentChunk(
        chunk_id=hit.chunk_id,
        doc_id=hit.doc_id or metadata.get("doc_id", hit.chunk_id),
        text=hit.text,
        position=max(position, 0),
        metadata=metadata,
    )
    return RetrievalResult(chunk=chunk, score=hit.score, retriever="vector")


class VectorRetriever:
    """Retrieve chunks from a vector store as ranked ``RetrievalResult``s."""

    def __init__(self, store: BaseVectorStore) -> None:
        self.store = store

    def retrieve(
        self,
        query: str,
        top_k: int = constants.DEFAULT_TOP_K,
        filters: dict | None = None,
    ) -> list[RetrievalResult]:
        """Return up to ``top_k`` chunks most relevant to ``query``.

        ``filters`` is an optional equality filter over chunk metadata, e.g.
        ``{"document_type": "skills"}``. An empty query or empty store yields ``[]``.
        """
        query = (query or "").strip()
        if not query:
            return []
        hits = self.store.query(query, top_k=top_k, filters=filters)
        return [_hit_to_result(hit) for hit in hits]


def retrieve(
    query: str,
    top_k: int = constants.DEFAULT_TOP_K,
    filters: dict | None = None,
    *,
    config: CopilotConfig | None = None,
    store: BaseVectorStore | None = None,
) -> list[RetrievalResult]:
    """Convenience one-shot retrieval.

    Builds a vector store from ``config`` when one is not supplied (mainly for
    scripts and the UI). Tests inject ``store`` directly.
    """
    if store is None:
        if config is None:
            raise ValueError("retrieve() needs either a store or a config")
        store = build_vector_store(config)
    return VectorRetriever(store).retrieve(query, top_k=top_k, filters=filters)
