"""Phase 3 tests: embeddings, vector store/retrieval, RAG chain, grounding.

All LLM calls are mocked via a fake responder; embeddings use the offline local
embedder and an in-memory (or temp Chroma) store, so tests are network-free.
"""

import pytest

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.embeddings import LocalHashEmbedder, build_embedder
from src.copilot.models import Citation, DocumentChunk, RetrievalResult
from src.copilot.rag.chain import ModelReply, RagChain, RagChainError
from src.copilot.rag.context import build_context
from src.copilot.rag.prompts import build_messages, system_prompt
from src.copilot.retrieval.vector import VectorRetriever
from src.copilot.vectorstore import InMemoryVectorStore, sanitize_metadata


def _chunk(chunk_id: str, text: str, **metadata) -> DocumentChunk:
    return DocumentChunk(
        chunk_id=chunk_id,
        doc_id=metadata.get("source_id", "doc"),
        text=text,
        position=metadata.get("chunk_index", 0),
        metadata=metadata,
    )


def _store_with(*chunks) -> InMemoryVectorStore:
    store = InMemoryVectorStore(LocalHashEmbedder())
    store.add_chunks(list(chunks))
    return store


# --- Embeddings --------------------------------------------------------------


class TestEmbeddings:
    def test_local_embedder_is_deterministic_and_sized(self) -> None:
        emb = LocalHashEmbedder()
        v1 = emb.embed_query("nursing triage skills")
        v2 = emb.embed_query("nursing triage skills")
        assert v1 == v2
        assert len(v1) == constants.LOCAL_EMBEDDING_DIMENSIONS

    def test_similar_text_scores_higher_than_unrelated(self) -> None:
        emb = LocalHashEmbedder()

        def cos(a, b):
            return sum(x * y for x, y in zip(a, b))

        q = emb.embed_query("data analysis and statistics skills")
        near = emb.embed_documents(["skills in data analysis and statistics"])[0]
        far = emb.embed_documents(["baking sourdough bread at home"])[0]
        assert cos(q, near) > cos(q, far)

    def test_build_embedder_falls_back_to_local_without_key(self) -> None:
        config = CopilotConfig()  # no api key
        emb = build_embedder(config)
        assert emb.provider == "local"

    def test_build_embedder_local_when_requested(self) -> None:
        config = CopilotConfig(embedding_provider="local")
        assert build_embedder(config).provider == "local"


# --- Index + store -----------------------------------------------------------


class TestIndexAndStore:
    def test_index_flow_adds_and_skips_existing(self) -> None:
        store = InMemoryVectorStore(LocalHashEmbedder())
        chunks = [_chunk("a", "first"), _chunk("b", "second")]
        first = store.add_chunks(chunks)
        assert first.added == 2 and first.total == 2
        # Re-indexing identical ids must not re-add (avoid re-indexing unchanged).
        second = store.add_chunks(chunks)
        assert second.added == 0
        assert second.skipped_existing == 2
        assert store.count() == 2

    def test_sanitize_metadata_keeps_scalars_only(self) -> None:
        clean = sanitize_metadata(
            {"title": "T", "page": 3, "nested": {"x": 1}, "list": [1, 2]},
            doc_id="d1",
        )
        assert clean["title"] == "T"
        assert clean["page"] == 3
        assert clean["doc_id"] == "d1"
        assert "nested" not in clean and "list" not in clean


# --- Retrieval ---------------------------------------------------------------


class TestRetrieval:
    def test_retrieve_ranks_relevant_chunk_first(self) -> None:
        store = _store_with(
            _chunk("s", "cloud infrastructure and kubernetes deployment skills",
                   title="Skills", document_type="skills"),
            _chunk("o", "gardening tips for growing tomatoes", title="Garden"),
        )
        results = VectorRetriever(store).retrieve("kubernetes deployment skills", top_k=2)
        assert results
        assert results[0].chunk.chunk_id == "s"
        assert isinstance(results[0], RetrievalResult)

    def test_metadata_filter_restricts_results(self) -> None:
        store = _store_with(
            _chunk("a", "leadership and strategy", document_type="occupation", title="A"),
            _chunk("b", "leadership and strategy", document_type="skills", title="B"),
        )
        results = VectorRetriever(store).retrieve(
            "leadership strategy", top_k=5, filters={"document_type": "skills"}
        )
        assert results
        assert all(r.metadata.get("document_type") == "skills" for r in results)

    def test_empty_query_and_empty_store_return_no_results(self) -> None:
        store = _store_with(_chunk("a", "content"))
        assert VectorRetriever(store).retrieve("", top_k=5) == []
        empty = InMemoryVectorStore(LocalHashEmbedder())
        assert VectorRetriever(empty).retrieve("anything", top_k=5) == []

    def test_result_exposes_provenance_accessors(self) -> None:
        store = _store_with(
            _chunk("a", "text here", title="Report", page=14, source="report.pdf")
        )
        r = VectorRetriever(store).retrieve("text", top_k=1)[0]
        assert r.title == "Report"
        assert r.page == 14
        assert r.source == "report.pdf"
        assert r.text == "text here"


# --- Context + citations -----------------------------------------------------


class TestContextAndCitations:
    def test_context_numbers_passages_and_maps_citations(self) -> None:
        results = [
            RetrievalResult(chunk=_chunk("a", "Alpha evidence", title="A", page=1), score=0.9),
            RetrievalResult(chunk=_chunk("b", "Beta evidence", title="B", page=2), score=0.8),
        ]
        bundle = build_context(results)
        assert "[1]" in bundle.context_text and "[2]" in bundle.context_text
        assert [c.marker for c in bundle.citations] == ["[1]", "[2]"]
        assert bundle.citations[0].chunk_id == "a"
        assert bundle.citations[1].page == 2

    def test_context_respects_char_budget(self) -> None:
        results = [
            RetrievalResult(chunk=_chunk(str(i), "word " * 200, title=f"T{i}"), score=1.0)
            for i in range(10)
        ]
        bundle = build_context(results, max_chars=500)
        # Not all 10 passages fit within a 500-char budget.
        assert 0 < len(bundle.used) < 10

    def test_citation_label_formats_with_page(self) -> None:
        c = Citation(marker="[1]", doc_id="d", chunk_id="c", title="WEF report", page=14)
        assert c.label == "[1] WEF report — page 14"

    def test_citation_label_links_to_source_url(self) -> None:
        c = Citation(
            marker="[1]", doc_id="d", chunk_id="c", title="WEF report",
            source_url="https://example.org/report", page=14,
        )
        assert c.label == "[1] [WEF report](https://example.org/report) — page 14"

    def test_context_populates_source_url_from_metadata(self) -> None:
        results = [
            RetrievalResult(
                chunk=_chunk("a", "Alpha", title="A", source_url="https://ex.org/a"),
                score=0.9,
            )
        ]
        bundle = build_context(results)
        assert bundle.citations[0].source_url == "https://ex.org/a"

    def test_context_resolves_source_url_from_manifest_source_id(self) -> None:
        # A chunk tagged with a manifest source_id resolves to that source's URL.
        results = [
            RetrievalResult(chunk=_chunk("a", "Alpha", title="O*NET", source_id="onet"), score=0.9)
        ]
        bundle = build_context(results)
        assert bundle.citations[0].source_url  # resolved from data/source_manifest.json


# --- Grounding prompt --------------------------------------------------------


class TestGroundingPrompt:
    def test_system_prompt_contains_grounding_rules(self) -> None:
        prompt = system_prompt()
        assert constants.INSUFFICIENT_EVIDENCE_MESSAGE in prompt
        assert "ONLY the numbered CONTEXT" in prompt
        assert "Never" in prompt and "invent a citation" in prompt

    def test_build_messages_places_context_in_user_turn(self) -> None:
        messages = build_messages("What skills matter?", "[1] Skills\nEvidence.")
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "CONTEXT:" in messages[1]["content"]
        assert "[1] Skills" in messages[1]["content"]

    def test_build_messages_flags_no_context(self) -> None:
        messages = build_messages("Question?", "")
        assert "No context passages were retrieved" in messages[1]["content"]


# --- RAG chain (mocked LLM) --------------------------------------------------


class TestRagChain:
    def test_chain_returns_only_referenced_citations(self) -> None:
        store = _store_with(
            _chunk("a", "Cloud skills are in demand.", title="Skills", page=1),
            _chunk("b", "Leadership matters.", title="Leadership", page=2),
        )
        chain = RagChain(
            VectorRetriever(store),
            responder=lambda messages: ModelReply(content="Cloud skills are rising [1]."),
        )
        response = chain.answer("What cloud skills are in demand?")
        assert response.answer.endswith("[1].")
        # Only the cited marker [1] is returned, not [2].
        assert [c.marker for c in response.citations] == ["[1]"]
        assert response.citations[0].chunk_id in {r.chunk.chunk_id for r in response.retrieved}
        assert response.translated_query.original_query == "What cloud skills are in demand?"

    def test_chain_reuses_supplied_results(self) -> None:
        store = _store_with(_chunk("a", "Evidence text about data roles.", title="Data"))
        chain = RagChain(
            VectorRetriever(store),
            responder=lambda m: ModelReply(content="Answer with no markers."),
        )
        results = chain.retrieve("data roles")
        response = chain.answer("data roles", results=results)
        assert response.retrieved == results
        assert response.citations == []  # no markers referenced

    def test_missing_evidence_behaviour_with_empty_store(self) -> None:
        empty = InMemoryVectorStore(LocalHashEmbedder())
        captured = {}

        def responder(messages):
            captured["user"] = messages[1]["content"]
            return ModelReply(content=constants.INSUFFICIENT_EVIDENCE_MESSAGE)

        chain = RagChain(VectorRetriever(empty), responder=responder)
        response = chain.answer("Totally unknown question?")
        assert response.retrieved == []
        assert "No context passages were retrieved" in captured["user"]
        assert response.answer == constants.INSUFFICIENT_EVIDENCE_MESSAGE
        assert response.citations == []

    def test_usage_is_passed_through(self) -> None:
        from src.copilot.models import UsageRecord

        store = _store_with(_chunk("a", "text", title="T"))
        usage = UsageRecord(model="m", prompt_tokens=10, completion_tokens=5, total_tokens=15)
        chain = RagChain(
            VectorRetriever(store),
            responder=lambda m: ModelReply(content="ok [1]", usage=usage),
        )
        response = chain.answer("text")
        assert response.usage is not None
        assert response.usage.total_tokens == 15

    def test_empty_query_raises(self) -> None:
        store = _store_with(_chunk("a", "text"))
        chain = RagChain(VectorRetriever(store), responder=lambda m: ModelReply("x"))
        with pytest.raises(RagChainError):
            chain.answer("   ")


# --- Persistent Chroma backend ----------------------------------------------


class TestChromaStore:
    def test_persist_dedup_and_query(self, tmp_path) -> None:
        chromadb = pytest.importorskip("chromadb")
        from src.copilot.vectorstore import ChromaStore

        embedder = LocalHashEmbedder()
        store = ChromaStore(embedder, persist_dir=str(tmp_path / "chroma"))
        chunks = [
            _chunk("a", "kubernetes and cloud deployment", title="Cloud", document_type="skills"),
            _chunk("b", "tomato gardening basics", title="Garden"),
        ]
        result = store.add_chunks(chunks)
        assert result.added == 2
        # Dedup across a second call.
        assert store.add_chunks(chunks).added == 0

        hits = store.query("cloud deployment kubernetes", top_k=1)
        assert hits and hits[0].chunk_id == "a"
        assert hits[0].metadata.get("document_type") == "skills"

        # Reopening the same path sees persisted data.
        reopened = ChromaStore(embedder, persist_dir=str(tmp_path / "chroma"))
        assert reopened.count() == 2
