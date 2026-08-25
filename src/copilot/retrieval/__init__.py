"""Retrieval package for Career Intelligence Copilot.

Phase 3 ships vector retrieval only. Hybrid (keyword + vector) search arrives in
a later phase behind the same :class:`RetrievalResult` interface.
"""

from src.copilot.retrieval.vector import VectorRetriever, retrieve

__all__ = ["VectorRetriever", "retrieve"]
