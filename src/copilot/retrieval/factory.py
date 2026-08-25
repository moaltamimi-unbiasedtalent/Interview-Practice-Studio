"""Retriever selection: build a vector, keyword or hybrid retriever.

All three expose the same ``retrieve(query, top_k, filters)`` method, so they are
interchangeable in the RAG chain and the evaluation harness. Hybrid is the
default; the single-channel retrievers are kept for testing and evaluation.
"""

from __future__ import annotations

from typing import Protocol

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.models import RetrievalResult
from src.copilot.retrieval.hybrid import HybridRetriever
from src.copilot.retrieval.keyword import KeywordRetriever
from src.copilot.retrieval.vector import VectorRetriever
from src.copilot.vectorstore import BaseVectorStore, build_vector_store

__all__ = ["Retriever", "build_retriever"]


class Retriever(Protocol):
    """The common retriever interface used by the chain and evaluation."""

    def retrieve(
        self, query: str, top_k: int = ..., filters: dict | None = ...
    ) -> list[RetrievalResult]:
        ...


def build_retriever(
    config: CopilotConfig,
    *,
    mode: str | None = None,
    store: BaseVectorStore | None = None,
) -> Retriever:
    """Build the retriever for ``mode`` (defaults to ``config.retrieval_mode``).

    A single vector store is shared across channels so vector and BM25 index the
    same chunks.
    """
    mode = (mode or config.retrieval_mode or constants.DEFAULT_RETRIEVAL_MODE).lower()
    if mode not in constants.RETRIEVAL_MODES:
        raise ValueError(
            f"Unknown retrieval mode {mode!r}; expected one of {constants.RETRIEVAL_MODES}."
        )

    store = store or build_vector_store(config)
    vector = VectorRetriever(store)
    if mode == "vector":
        return vector

    keyword = KeywordRetriever.from_store(store)
    if mode == "keyword":
        return keyword

    return HybridRetriever(
        vector,
        keyword,
        vector_weight=config.hybrid_vector_weight,
        keyword_weight=config.hybrid_keyword_weight,
    )
