"""Phase 11R tests: RAG evaluation metric maths + evaluators (offline)."""

import json

from src.copilot.embeddings import LocalHashEmbedder
from src.copilot.evaluation.rag_eval import (
    ToolCase,
    evaluate_citations,
    evaluate_retrieval,
    evaluate_tool_selection,
    grounding_metrics,
    hit_rate_at_k,
    load_dataset,
    recall_at_k,
    reciprocal_rank,
)
from src.copilot.ingestion import indexer
from src.copilot.retrieval import build_retriever
from src.copilot.config import CopilotConfig
from src.copilot.vectorstore import build_vector_store


# --- Pure metric maths -------------------------------------------------------


class TestMetrics:
    def test_hit_rate(self) -> None:
        assert hit_rate_at_k(["a", "b", "c"], {"c"}, 5) == 1.0
        assert hit_rate_at_k(["a", "b", "c"], {"z"}, 5) == 0.0
        assert hit_rate_at_k(["a", "b", "c"], {"c"}, 2) == 0.0  # c is rank 3, k=2

    def test_reciprocal_rank(self) -> None:
        assert reciprocal_rank(["x", "a", "b"], {"a"}, 5) == 0.5  # rank 2
        assert reciprocal_rank(["a", "b"], {"a"}, 5) == 1.0
        assert reciprocal_rank(["a", "b"], {"z"}, 5) == 0.0

    def test_recall(self) -> None:
        assert recall_at_k(["a", "b", "c"], {"a", "z"}, 5) == 0.5  # 1 of 2
        assert recall_at_k(["a", "b"], {"a", "b"}, 5) == 1.0
        assert recall_at_k(["a"], set(), 5) == 0.0  # no relevant → 0

    def test_grounding_metrics(self) -> None:
        m = grounding_metrics("Skills are rising [1]. This is general advice.", ["[1]"])
        assert m["sentences"] == 2 and m["cited_sentences"] == 1
        assert m["citation_coverage"] == 0.5


# --- Dataset -----------------------------------------------------------------


class TestDataset:
    def test_dataset_loads_with_enough_cases(self) -> None:
        cases, top_k = load_dataset("evaluations/rag_dataset.json")
        assert len(cases) >= 25
        assert top_k >= 1
        categories = {c.category for c in cases}
        for expected in (
            "semantic_career", "exact_skill", "occupation", "labour_market",
            "cross_document", "acronym_phrase", "translation_benefit",
        ):
            assert expected in categories, expected
        for c in cases:  # ground truth present
            assert c.expected_sources or c.expected_terms


# --- Evaluators over the committed corpus ------------------------------------


def _corpus_store():
    config = CopilotConfig(embedding_provider="local")
    store = build_vector_store(config, embedder=LocalHashEmbedder(), in_memory=True)
    chunks, _ = indexer.ingest_directory("evaluations/corpus")
    store.add_chunks(chunks)
    return config, store


class TestEvaluators:
    def test_retrieval_metrics_shape(self) -> None:
        config, store = _corpus_store()
        cases, top_k = load_dataset("evaluations/rag_dataset.json")
        retrievers = {m: build_retriever(config, mode=m, store=store) for m in ("vector", "keyword", "hybrid")}
        metrics = evaluate_retrieval(retrievers, cases[:6], top_k)
        assert set(metrics) == {"vector", "keyword", "hybrid"}
        for m in metrics.values():
            assert 0.0 <= m.hit_rate_at_k <= 1.0
            assert 0.0 <= m.mrr <= 1.0
            assert m.avg_latency_ms >= 0.0

    def test_citation_validity_is_perfect_by_construction(self) -> None:
        config, store = _corpus_store()
        cases, top_k = load_dataset("evaluations/rag_dataset.json")
        result = evaluate_citations(build_retriever(config, mode="hybrid", store=store), cases[:6], top_k)
        assert result["valid_id_mapping_rate"] == 1.0

    def test_tool_selection_accuracy(self) -> None:
        with open("evaluations/tool_selection_cases.json", encoding="utf-8") as f:
            cases = [ToolCase(**c) for c in json.load(f)["cases"]]
        result = evaluate_tool_selection(cases)
        assert result["accuracy"] == 1.0  # deterministic routing matches expectations
