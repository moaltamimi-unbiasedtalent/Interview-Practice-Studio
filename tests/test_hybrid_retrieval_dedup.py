"""Phase 5 regression: no duplicate hybrid retrieval for the Inspector.

For a single rewritten query, the hybrid retriever's search() must run once — its
result feeds both the answer fusion and the RAG Inspector channels. Only extra
translated query variants may trigger additional retrieval.
"""

from __future__ import annotations

import json

from src.copilot.config import CopilotConfig
from src.copilot.embeddings import LocalHashEmbedder
from src.copilot.models import DocumentChunk
from src.copilot.rag.responder import ModelReply
from src.copilot.rag.translation import QueryTranslator
from src.copilot.retrieval import build_retriever
from src.copilot.service import CareerIntelligenceService
from src.copilot.vectorstore import InMemoryVectorStore

CONFIG = CopilotConfig()


def _store() -> InMemoryVectorStore:
    store = InMemoryVectorStore(LocalHashEmbedder())
    store.add_chunks([
        DocumentChunk(chunk_id="ai", doc_id="d1",
                      text="Demand for AI and machine learning skills is rising.",
                      metadata={"title": "AI demand", "document_type": "labour_market"}),
        DocumentChunk(chunk_id="lead", doc_id="d2",
                      text="Leadership needs communication and stakeholder management.",
                      metadata={"title": "Leadership", "document_type": "occupation"}),
    ])
    return store


def _translator(*, alternates):
    payload = {"intent": "skill_research", "retrieval_required": True,
               "rewritten_query": "AI machine learning skills",
               "alternate_queries": alternates, "metadata_filters": {},
               "explanation": "ok"}
    return QueryTranslator(responder=lambda m: ModelReply(content=json.dumps(payload)))


class _CountingHybrid:
    """Wrap a real hybrid retriever, counting search() calls."""

    def __init__(self, inner):
        self._inner = inner
        self.search_calls = 0

    def search(self, query, top_k=5, filters=None):
        self.search_calls += 1
        return self._inner.search(query, top_k=top_k, filters=filters)

    def retrieve(self, query, top_k=5, filters=None):
        return self.search(query, top_k=top_k, filters=filters).fused


def _service(retriever, translator):
    return CareerIntelligenceService(
        config=CONFIG, retriever=retriever, translator=translator,
        synthesis_responder=lambda m: ModelReply(content="Answer [1]."))


def test_single_query_does_not_duplicate_hybrid_search() -> None:
    from src.copilot.retrieval.hybrid import HybridRetriever

    inner = build_retriever(CONFIG, mode="hybrid", store=_store())
    assert isinstance(inner, HybridRetriever)
    counting = _CountingHybrid(inner)
    # Make isinstance(retriever, HybridRetriever) true for the service path.
    counting.__class__ = type("CountingHybrid", (HybridRetriever,),
                              dict(_CountingHybrid.__dict__))

    result = _service(counting, _translator(alternates=[])).answer(
        "What skills are in demand?")
    assert result.trace.retrieval_strategy == "hybrid"
    # Inspector channels populated from the SAME single search (no re-search).
    assert result.trace.vector_results or result.trace.keyword_results
    assert counting.search_calls == 1  # exactly one hybrid search for one query


def test_alternate_queries_each_retrieve_once() -> None:
    from src.copilot.retrieval.hybrid import HybridRetriever

    inner = build_retriever(CONFIG, mode="hybrid", store=_store())
    counting = _CountingHybrid(inner)
    counting.__class__ = type("CountingHybrid", (HybridRetriever,),
                              dict(_CountingHybrid.__dict__))

    _service(counting, _translator(alternates=["ml demand", "ai jobs"])).answer(
        "What skills are in demand?")
    # 1 primary + 2 alternates = 3 searches (no extra inspector re-search).
    assert counting.search_calls == 3
