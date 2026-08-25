"""Phase 5 tests: BM25 keyword retrieval, hybrid fusion, retriever selection.

Uses the offline local embedder + in-memory vector store so vector and BM25
index the same chunks with no network. rank-bm25 is required for the keyword
channel and is skipped cleanly if unavailable.
"""

import pytest

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.embeddings import LocalHashEmbedder
from src.copilot.evaluation import RetrievalProbe, evaluate_modes
from src.copilot.models import DocumentChunk
from src.copilot.retrieval import build_retriever
from src.copilot.retrieval.fusion import reciprocal_rank_fusion
from src.copilot.retrieval.hybrid import HybridRetriever
from src.copilot.retrieval.keyword import KeywordRetriever, tokenize
from src.copilot.retrieval.vector import VectorRetriever
from src.copilot.vectorstore import InMemoryVectorStore

pytest.importorskip("rank_bm25")


CORPUS = [
    ("py", "Python is a popular programming language for data analysis and scripting.", "skills"),
    ("sql", "SQL is used to query relational databases; strong SQL skills are in demand.", "skills"),
    ("iso", "ISO 27001 is an information security management standard with specific controls.", "industry_report"),
    ("lead", "Senior leadership requires strategic vision, stakeholder management and communication.", "occupation"),
    ("sap", "SAP enterprise resource planning experience is valued in operations roles.", "occupation"),
    ("devops", "A DevOps engineer automates deployment pipelines and manages cloud infrastructure.", "occupation"),
]


def _chunk(chunk_id: str, text: str, doc_type: str) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        doc_id=chunk_id,
        text=text,
        metadata={"title": chunk_id, "document_type": doc_type},
    )


@pytest.fixture
def store() -> InMemoryVectorStore:
    store = InMemoryVectorStore(LocalHashEmbedder())
    store.add_chunks([_chunk(cid, text, dtype) for cid, text, dtype in CORPUS])
    return store


def _ids(results) -> list[str]:
    return [r.chunk.chunk_id for r in results]


# --- Tokeniser ---------------------------------------------------------------


def test_tokenizer_splits_codes_and_acronyms() -> None:
    assert tokenize("ISO 27001") == ["iso", "27001"]
    assert tokenize("SQL and Python!") == ["sql", "and", "python"]


# --- BM25 keyword ------------------------------------------------------------


class TestKeyword:
    def test_exact_keyword(self, store) -> None:
        kw = KeywordRetriever.from_store(store)
        results = kw.retrieve("SQL querying skills", top_k=5)
        assert results and results[0].chunk.chunk_id == "sql"
        assert results[0].retriever == "keyword"

    def test_acronym(self, store) -> None:
        kw = KeywordRetriever.from_store(store)
        assert "sap" in _ids(kw.retrieve("SAP experience", top_k=5))

    def test_rare_technology_code(self, store) -> None:
        kw = KeywordRetriever.from_store(store)
        # The rare token "27001" pins the ISO chunk.
        assert _ids(kw.retrieve("ISO 27001 controls", top_k=3))[0] == "iso"

    def test_no_lexical_overlap_returns_empty(self, store) -> None:
        kw = KeywordRetriever.from_store(store)
        assert kw.retrieve("zzzzz nonexistent term", top_k=5) == []

    def test_empty_query_and_empty_corpus(self, store) -> None:
        kw = KeywordRetriever.from_store(store)
        assert kw.retrieve("", top_k=5) == []
        assert KeywordRetriever([]).retrieve("anything", top_k=5) == []

    def test_metadata_filter(self, store) -> None:
        kw = KeywordRetriever.from_store(store)
        results = kw.retrieve("skills", top_k=5, filters={"document_type": "skills"})
        assert results
        assert all(r.metadata["document_type"] == "skills" for r in results)


# --- Vector (semantic, retained) --------------------------------------------


class TestVectorRetained:
    def test_semantic_query_still_works(self, store) -> None:
        vec = VectorRetriever(store)
        results = vec.retrieve("leadership strategic vision communication", top_k=3)
        assert results and results[0].chunk.chunk_id == "lead"


# --- Hybrid ------------------------------------------------------------------


class TestHybrid:
    def _hybrid(self, store) -> HybridRetriever:
        return HybridRetriever(VectorRetriever(store), KeywordRetriever.from_store(store))

    def test_search_exposes_all_channels(self, store) -> None:
        detail = self._hybrid(store).search("SQL skills", top_k=5)
        assert detail.vector and detail.keyword and detail.fused
        assert all(r.retriever == "hybrid" for r in detail.fused)

    def test_fusion_deduplicates(self, store) -> None:
        detail = self._hybrid(store).search("SQL skills in demand", top_k=6)
        fused_ids = _ids(detail.fused)
        assert len(fused_ids) == len(set(fused_ids))  # no duplicates
        # 'sql' is found by both channels; dedup keeps it once.
        assert fused_ids.count("sql") == 1

    def test_fusion_union_retains_vector_and_keyword(self, store) -> None:
        detail = self._hybrid(store).search("Python programming", top_k=10)
        union = set(_ids(detail.vector)) | set(_ids(detail.keyword))
        assert set(_ids(detail.fused)) == union

    def test_score_fusion_ranks_agreed_chunk_first(self, store) -> None:
        # A chunk surfaced highly by both channels should win under RRF.
        detail = self._hybrid(store).search("SQL databases", top_k=5)
        assert _ids(detail.fused)[0] == "sql"
        assert detail.fused[0].score > detail.fused[-1].score


# --- Fusion weights ----------------------------------------------------------


class TestFusionWeights:
    def test_weight_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            reciprocal_rank_fusion([[], []], weights=[1.0])

    def test_weights_shift_ranking(self, store) -> None:
        vec = VectorRetriever(store).retrieve("operations SAP", top_k=5)
        kw = KeywordRetriever.from_store(store).retrieve("operations SAP", top_k=5)
        keyword_heavy = reciprocal_rank_fusion([vec, kw], weights=[0.0, 1.0])
        # With vector weighted to zero, ranking follows the keyword channel.
        assert _ids(keyword_heavy)[: len(kw)] == _ids(kw)


# --- Retriever selection -----------------------------------------------------


class TestSelection:
    def test_modes_build_expected_types(self, store) -> None:
        config = CopilotConfig()
        assert isinstance(build_retriever(config, mode="vector", store=store), VectorRetriever)
        assert isinstance(build_retriever(config, mode="keyword", store=store), KeywordRetriever)
        assert isinstance(build_retriever(config, mode="hybrid", store=store), HybridRetriever)

    def test_default_mode_is_hybrid(self, store) -> None:
        config = CopilotConfig()
        assert config.retrieval_mode == "hybrid"
        assert isinstance(build_retriever(config, store=store), HybridRetriever)

    def test_unknown_mode_raises(self, store) -> None:
        with pytest.raises(ValueError):
            build_retriever(CopilotConfig(), mode="magic", store=store)


# --- Store corpus access -----------------------------------------------------


def test_all_chunks_roundtrips_metadata(store) -> None:
    chunks = store.all_chunks()
    assert len(chunks) == len(CORPUS)
    by_id = {c.chunk_id: c for c in chunks}
    assert by_id["iso"].metadata["document_type"] == "industry_report"


# --- Evaluation baseline -----------------------------------------------------


class TestEvaluationBaseline:
    def test_evaluate_modes_reports_all_three(self, store) -> None:
        config = CopilotConfig()
        retrievers = {
            m: build_retriever(config, mode=m, store=store)
            for m in constants.RETRIEVAL_MODES
        }
        probes = [
            RetrievalProbe(query="SQL querying", expected_terms=["SQL"]),
            RetrievalProbe(query="leadership communication", expected_terms=["leadership"]),
        ]
        metrics = evaluate_modes(retrievers, probes, top_k=5)
        assert set(metrics) == set(constants.RETRIEVAL_MODES)
        for m in metrics.values():
            assert 0.0 <= m.term_recall_at_k <= 1.0
            assert m.probes == 2
        # Keyword must find the exact term "SQL" for that probe.
        assert metrics["keyword"].term_recall_at_k > 0.0
