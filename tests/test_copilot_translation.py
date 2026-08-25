"""Phase 4 tests: query translation, multi-query fusion, safe filters.

The translation LLM is mocked with a fake responder that returns canned JSON, so
tests are deterministic and network-free.
"""

import json

from src.copilot import constants
from src.copilot.embeddings import LocalHashEmbedder
from src.copilot.models import DocumentChunk, RetrievalResult
from src.copilot.rag.chain import RagChain
from src.copilot.rag.responder import ModelReply
from src.copilot.rag.translation import (
    QueryTranslator,
    heuristic_translation,
    sanitize_filters,
)
from src.copilot.retrieval.fusion import reciprocal_rank_fusion
from src.copilot.retrieval.vector import VectorRetriever
from src.copilot.vectorstore import InMemoryVectorStore


def _responder(payload: dict):
    """A fake responder that returns ``payload`` serialised as JSON."""
    return lambda messages: ModelReply(content=json.dumps(payload))


def _chunk(chunk_id: str, text: str, **metadata) -> DocumentChunk:
    return DocumentChunk(chunk_id=chunk_id, doc_id="d", text=text, metadata=metadata)


def _result(chunk_id: str, score: float = 1.0) -> RetrievalResult:
    return RetrievalResult(chunk=_chunk(chunk_id, f"text {chunk_id}"), score=score)


# --- Filters -----------------------------------------------------------------


class TestSanitizeFilters:
    def test_keeps_allowed_field_with_allowed_value(self) -> None:
        assert sanitize_filters({"document_type": "skills"}) == {"document_type": "skills"}

    def test_drops_unknown_fields_and_bad_values(self) -> None:
        raw = {
            "document_type": "not_a_real_type",  # invalid value
            "year": 2020,  # not in the whitelist
            "DROP TABLE": "x",  # not a field
        }
        assert sanitize_filters(raw) == {}

    def test_non_dict_returns_empty(self) -> None:
        assert sanitize_filters("document_type=skills") == {}
        assert sanitize_filters(None) == {}


# --- LLM translation (mocked) ------------------------------------------------


class TestTranslation:
    def test_simple_query_passthrough_rewrite(self) -> None:
        payload = {
            "intent": "factual_career",
            "retrieval_required": True,
            "rewritten_query": "What is a product manager's typical salary range",
            "alternate_queries": [],
            "metadata_filters": {},
            "explanation": "Clarified the query for retrieval.",
        }
        tq = QueryTranslator(responder=_responder(payload)).translate(
            "product manager salary?"
        )
        assert tq.strategy == "llm"
        assert tq.intent == "factual_career"
        assert tq.retrieval_required is True
        assert tq.alternate_queries == []
        assert tq.all_queries == [payload["rewritten_query"]]

    def test_ambiguous_query_is_rewritten_clearer(self) -> None:
        payload = {
            "intent": "skill_research",
            "retrieval_required": True,
            "rewritten_query": (
                "Skills, technical competencies and knowledge required for AI "
                "engineering roles"
            ),
            "alternate_queries": [],
            "metadata_filters": {"document_type": "skills"},
            "explanation": "Expanded an ambiguous query into a specific skills query.",
        }
        tq = QueryTranslator(responder=_responder(payload)).translate(
            "What should I learn for AI?"
        )
        assert "AI engineering" in tq.rewritten_query
        assert tq.metadata_filters == {"document_type": "skills"}

    def test_broad_query_generates_two_to_four_queries(self) -> None:
        payload = {
            "intent": "skill_research",
            "retrieval_required": True,
            "rewritten_query": "AI engineer technical skills",
            "alternate_queries": [
                "AI engineering role competencies",
                "future demand for AI skills",
                "machine learning engineer required knowledge",
            ],
            "metadata_filters": {},
            "explanation": "Generated several angles for a broad question.",
        }
        tq = QueryTranslator(responder=_responder(payload)).translate(
            "Tell me everything about AI careers"
        )
        assert 2 <= len(tq.all_queries) <= 4

    def test_role_query_infers_safe_filter(self) -> None:
        payload = {
            "intent": "role_research",
            "retrieval_required": True,
            "rewritten_query": "Responsibilities and skills of operations managers",
            "alternate_queries": ["operations manager duties"],
            "metadata_filters": {"document_type": "occupation"},
            "explanation": "Focused on the occupation category.",
        }
        tq = QueryTranslator(responder=_responder(payload)).translate(
            "what does an operations manager do?"
        )
        assert tq.intent == "role_research"
        assert tq.metadata_filters == {"document_type": "occupation"}

    def test_no_retrieval_query(self) -> None:
        payload = {
            "intent": "smalltalk",
            "retrieval_required": True,  # even if the model says True…
            "rewritten_query": "hello",
            "alternate_queries": [],
            "metadata_filters": {},
            "explanation": "Greeting.",
        }
        tq = QueryTranslator(responder=_responder(payload)).translate("hello there")
        # …smalltalk intent forces retrieval off.
        assert tq.retrieval_required is False

    def test_alternates_dedup_and_cap(self) -> None:
        payload = {
            "intent": "skill_research",
            "retrieval_required": True,
            "rewritten_query": "data analyst skills",
            "alternate_queries": [
                "data analyst skills",  # duplicate of rewritten -> dropped
                "data analyst competencies",
                "data analyst competencies",  # duplicate alt -> dropped
                "skills for data analysts",
                "data analysis toolkit",
                "extra query beyond the cap",
            ],
            "metadata_filters": {},
            "explanation": "ok",
        }
        tq = QueryTranslator(responder=_responder(payload)).translate("data analyst")
        assert len(tq.alternate_queries) <= constants.MAX_ALTERNATE_QUERIES
        assert "data analyst skills" not in tq.alternate_queries

    def test_arbitrary_filters_are_stripped(self) -> None:
        payload = {
            "intent": "role_research",
            "retrieval_required": True,
            "rewritten_query": "engineer roles",
            "alternate_queries": [],
            "metadata_filters": {"document_type": "occupation", "hacked": "1=1"},
            "explanation": "ok",
        }
        tq = QueryTranslator(responder=_responder(payload)).translate("engineer roles")
        assert tq.metadata_filters == {"document_type": "occupation"}

    def test_malformed_translation_falls_back(self) -> None:
        responder = lambda messages: ModelReply(content="not json at all <>")
        tq = QueryTranslator(responder=responder).translate("What skills for nursing?")
        assert tq.strategy == "heuristic"  # fell back
        assert tq.rewritten_query  # still usable

    def test_responder_exception_falls_back(self) -> None:
        def responder(messages):
            raise RuntimeError("network down")

        tq = QueryTranslator(responder=responder).translate("What skills for nursing?")
        assert tq.strategy == "heuristic"
        assert tq.retrieval_required is True

    def test_disabled_uses_heuristic(self) -> None:
        tq = QueryTranslator(enabled=False).translate("interview tips for managers")
        assert tq.strategy == "heuristic"
        assert tq.intent == "interview_preparation"


class TestHeuristic:
    def test_smalltalk_detected(self) -> None:
        tq = heuristic_translation("hello")
        assert tq.intent == "smalltalk" and tq.retrieval_required is False

    def test_skill_intent_and_filter(self) -> None:
        tq = heuristic_translation("what skills do data analysts need?")
        assert tq.intent == "skill_research"
        assert tq.metadata_filters == {"document_type": "skills"}


# --- Fusion ------------------------------------------------------------------


class TestFusion:
    def test_rrf_dedups_and_ranks(self) -> None:
        list1 = [_result("a"), _result("b")]
        list2 = [_result("a"), _result("c")]
        fused = reciprocal_rank_fusion([list1, list2])
        ids = [r.chunk.chunk_id for r in fused]
        assert ids == ["a", "b", "c"]  # 'a' appears once, ranked first
        assert fused[0].retriever == "fusion"
        assert fused[0].score > fused[1].score  # 'a' scored by both lists

    def test_rrf_respects_top_k(self) -> None:
        lists = [[_result("a"), _result("b"), _result("c")]]
        fused = reciprocal_rank_fusion(lists, top_k=2)
        assert len(fused) == 2

    def test_rrf_empty(self) -> None:
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []


# --- Chain integration -------------------------------------------------------


def _store_with(*chunks) -> InMemoryVectorStore:
    store = InMemoryVectorStore(LocalHashEmbedder())
    store.add_chunks(list(chunks))
    return store


class TestChainWithTranslation:
    def test_no_retrieval_intent_skips_search(self) -> None:
        store = _store_with(_chunk("a", "some evidence", title="A"))
        translator = QueryTranslator(enabled=False)  # heuristic
        chain = RagChain(
            VectorRetriever(store),
            translator=translator,
            responder=lambda m: ModelReply(content="Hi! How can I help?"),
        )
        response = chain.answer("hello")
        assert response.translated_query.retrieval_required is False
        assert response.retrieved == []

    def test_multi_query_retrieval_is_fused(self) -> None:
        store = _store_with(
            _chunk("k", "kubernetes and cloud deployment skills", title="Cloud",
                   document_type="skills"),
            _chunk("m", "machine learning model training skills", title="ML",
                   document_type="skills"),
        )
        payload = {
            "intent": "skill_research",
            "retrieval_required": True,
            "rewritten_query": "cloud deployment skills",
            "alternate_queries": ["machine learning model training"],
            "metadata_filters": {"document_type": "skills"},
            "explanation": "Broadened the search.",
        }
        chain = RagChain(
            VectorRetriever(store),
            translator=QueryTranslator(responder=_responder(payload)),
            responder=lambda m: ModelReply(content="Cloud and ML skills matter [1]."),
        )
        response = chain.answer("what skills?")
        assert response.translated_query.intent == "skill_research"
        assert len(response.translated_query.all_queries) == 2
        # Both distinct chunks surface via fusion; no duplicates.
        ids = [r.chunk.chunk_id for r in response.retrieved]
        assert set(ids) == {"k", "m"}
        assert len(ids) == len(set(ids))
        assert all(r.retriever == "fusion" for r in response.retrieved)
