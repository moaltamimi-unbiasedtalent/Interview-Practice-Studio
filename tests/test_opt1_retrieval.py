"""OPT-1: embedding status, reranker interface, adaptive signals, section chunking."""

from __future__ import annotations

from pydantic import SecretStr

from src.copilot.config import CopilotConfig
from src.copilot.embeddings import embedding_status
from src.copilot.ingestion.chunking import chunk_units
from src.copilot.ingestion.loaders import LoadedUnit
from src.copilot.models import DocumentChunk, RetrievalResult
from src.copilot.retrieval.adaptive import classify_weight_signal, dominant_signal
from src.copilot.retrieval.reranker import (
    LLMReranker,
    NoOpReranker,
    build_reranker,
)


# --- Embedding status (OPT-1A) ----------------------------------------------


class TestEmbeddingStatus:
    def test_local_is_offline_lexical(self) -> None:
        s = embedding_status(CopilotConfig(embedding_provider="local"))
        assert s["quality_mode"] == "OFFLINE LEXICAL" and s["provider"] == "local"

    def test_auto_without_dedicated_key_is_lexical(self) -> None:
        s = embedding_status(CopilotConfig(embedding_provider="auto",
                                           api_key=SecretStr("sk-or-chatkey")))
        assert s["quality_mode"] == "OFFLINE LEXICAL"  # chat key is NOT an embed key

    def test_dedicated_key_is_semantic(self) -> None:
        s = embedding_status(CopilotConfig(embedding_provider="auto",
                                           embedding_api_key=SecretStr("sk-embed")))
        assert s["quality_mode"] == "SEMANTIC" and s["provider"] == "openai"

    def test_never_returns_key_contents(self) -> None:
        s = embedding_status(CopilotConfig(embedding_api_key=SecretStr("sk-secret-123")))
        assert "sk-secret-123" not in json_dump(s)


def json_dump(obj) -> str:
    import json
    return json.dumps(obj)


# --- Reranker (OPT-1B) -------------------------------------------------------


def _results(n):
    return [RetrievalResult(chunk=DocumentChunk(chunk_id=str(i), doc_id="d", text=f"t{i}",
                                                position=i, metadata={}), score=1.0 - i * 0.1)
            for i in range(n)]


class TestReranker:
    def test_default_is_noop(self) -> None:
        assert isinstance(build_reranker(CopilotConfig()), NoOpReranker)

    def test_noop_preserves_order_and_topk(self) -> None:
        res = _results(6)
        out = NoOpReranker().rerank("q", res, top_k=3)
        assert [r.chunk.chunk_id for r in out.results] == ["0", "1", "2"]
        assert out.reranker_used is False and out.reranker_provider == "none"

    def test_llm_reranker_failure_returns_original_order(self) -> None:
        def boom(_):
            raise RuntimeError("model down")
        res = _results(5)
        out = LLMReranker(responder=boom).rerank("q", res, top_k=3)
        assert [r.chunk.chunk_id for r in out.results] == ["0", "1", "2"]  # RRF order kept
        assert out.reranker_used is False
        assert any("failed" in n for n in out.notes)

    def test_llm_reranker_reorders_on_valid_reply(self) -> None:
        from src.copilot.rag.responder import ModelReply
        res = _results(3)
        out = LLMReranker(responder=lambda m: ModelReply(content="[2,0,1]")).rerank(
            "q", res, top_k=3)
        assert [r.chunk.chunk_id for r in out.results] == ["2", "0", "1"]
        assert out.reranker_used is True and out.reranked_count == 3


# --- Adaptive weight signals (OPT-2A) ---------------------------------------


class TestAdaptiveSignals:
    def test_exact_token_heavy(self) -> None:
        code, v, k = classify_weight_signal("Do I need CISSP?", base_vector=1.0, base_keyword=1.0)
        assert code == "EXACT_TOKEN_HEAVY" and k > v

    def test_conceptual_query(self) -> None:
        code, v, k = classify_weight_signal(
            "Why is stakeholder management important and how do I develop it over time",
            base_vector=1.0, base_keyword=1.0)
        assert code == "CONCEPTUAL_QUERY" and v > k

    def test_default_equal(self) -> None:
        code, v, k = classify_weight_signal("data analyst tasks", base_vector=1.0, base_keyword=1.0)
        assert code == "DEFAULT_EQUAL" and v == k

    def test_dominant_signal_labels(self) -> None:
        res = _results(3)
        assert "keyword" in dominant_signal([], res, res).lower()
        assert "vector" in dominant_signal(res, [], res).lower()


# --- Section chunking (OPT-1C) ----------------------------------------------


class TestSectionChunking:
    def test_small_unit_kept_intact(self) -> None:
        units = [LoadedUnit(text="A short section about accountants.",
                            metadata={"section": "Overview", "title": "Doc"})]
        chunks = chunk_units(units, source_id="s", strategy="section")
        assert len(chunks) == 1
        assert chunks[0].metadata["section"] == "Overview"

    def test_oversized_unit_is_split(self) -> None:
        big = "word " * 3000  # exceeds section cap
        chunks = chunk_units([LoadedUnit(text=big, metadata={})], source_id="s",
                             strategy="section")
        assert len(chunks) > 1

    def test_baseline_still_default(self) -> None:
        units = [LoadedUnit(text="word " * 3000, metadata={})]
        base = chunk_units(units, source_id="s")  # default baseline
        assert len(base) > 1
