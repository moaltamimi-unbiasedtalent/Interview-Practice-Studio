"""Retrieval package for Career Intelligence Copilot.

Three interchangeable retrievers over the same chunks:

* :class:`VectorRetriever` — semantic / vector search.
* :class:`KeywordRetriever` — lexical BM25 search (exact terms, acronyms).
* :class:`HybridRetriever` — both, fused with reciprocal rank fusion (default).

:func:`build_retriever` selects the mode; :func:`reciprocal_rank_fusion` is the
explainable fusion used by both hybrid search and multi-query translation.
"""

from src.copilot.retrieval.factory import Retriever, build_retriever
from src.copilot.retrieval.fusion import reciprocal_rank_fusion
from src.copilot.retrieval.hybrid import HybridRetriever, HybridSearch
from src.copilot.retrieval.keyword import KeywordRetriever
from src.copilot.retrieval.vector import VectorRetriever, retrieve

__all__ = [
    "VectorRetriever",
    "KeywordRetriever",
    "HybridRetriever",
    "HybridSearch",
    "Retriever",
    "build_retriever",
    "reciprocal_rank_fusion",
    "retrieve",
]
