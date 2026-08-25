"""Phase 7 tests: mocked end-to-end orchestration (RAG + tools).

All LLM calls (translation, tool structured output, synthesis) are injected
fakes — no network, no paid API calls. Scenarios A–J mirror the phase spec.
"""

import json

import pytest

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.embeddings import LocalHashEmbedder
from src.copilot.models import DocumentChunk
from src.copilot.rag.responder import ModelReply
from src.copilot.rag.translation import QueryTranslator
from src.copilot.retrieval import build_retriever
from src.copilot.retrieval.hybrid import HybridRetriever
from src.copilot.retrieval.vector import VectorRetriever
from src.copilot.service import CareerIntelligenceService
from src.copilot.tools import ToolInvoker, build_tool_registry
from src.copilot.tools.schemas import InterviewQuestionSet, QuestionCategory, RoleRequirements
from src.copilot.vectorstore import InMemoryVectorStore

CONFIG = CopilotConfig()


# --- fixtures / fakes --------------------------------------------------------


def _corpus_store() -> InMemoryVectorStore:
    store = InMemoryVectorStore(LocalHashEmbedder())
    store.add_chunks(
        [
            DocumentChunk(
                chunk_id="ai",
                doc_id="d1",
                text="Demand for AI and machine learning skills is rising across the labour market.",
                metadata={"title": "AI demand", "document_type": "labour_market", "page": 1},
            ),
            DocumentChunk(
                chunk_id="lead",
                doc_id="d2",
                text="Leadership requires communication and stakeholder management.",
                metadata={"title": "Leadership", "document_type": "occupation"},
            ),
        ]
    )
    return store


def _empty_store() -> InMemoryVectorStore:
    return InMemoryVectorStore(LocalHashEmbedder())


def _translator(intent, *, rewritten="rewritten query", retrieval_required=True, raises=False):
    if raises:
        def boom(messages):
            raise RuntimeError("translation model down")

        return QueryTranslator(responder=boom)
    payload = {
        "intent": intent,
        "retrieval_required": retrieval_required,
        "rewritten_query": rewritten,
        "alternate_queries": [],
        "metadata_filters": {},
        "explanation": "ok",
    }
    return QueryTranslator(responder=lambda m: ModelReply(content=json.dumps(payload)))


def _fake_job(messages):
    return RoleRequirements(
        role_title="Data Engineer", required_skills=["Python", "SQL"], technologies=["AWS"]
    )


def _fake_questions(messages):
    return InterviewQuestionSet(
        role="Data Engineer",
        categories=[QuestionCategory(name="technical", questions=["Explain a pipeline."])],
    )


def _invoker(job_producer=_fake_job, question_producer=_fake_questions):
    return ToolInvoker(
        build_tool_registry(
            config=None, job_producer=job_producer, question_producer=question_producer
        )
    )


def _synth(text):
    return lambda messages: ModelReply(content=text)


def _service(*, store=None, retriever=None, translator=None, invoker=None, synth_text="OK."):
    store = store if store is not None else _corpus_store()
    retriever = retriever or build_retriever(CONFIG, mode="hybrid", store=store)
    return CareerIntelligenceService(
        config=CONFIG,
        retriever=retriever,
        translator=translator or _translator("skill_research"),
        tool_invoker=invoker or _invoker(),
        synthesis_responder=_synth(synth_text),
    )


# --- Scenarios ---------------------------------------------------------------


class TestOrchestration:
    def test_A_pure_rag(self) -> None:
        service = _service(
            translator=_translator("skill_research", rewritten="AI machine learning skill demand labour market"),
            synth_text="Evidence (from sources): AI skill demand is rising [1].",
        )
        result = service.answer("What does the evidence say about AI skill demand?")
        assert result.trace.rag_required is True
        assert result.trace.rag_used is True
        assert result.tool_calls == []  # no tools
        assert [c.marker for c in result.citations] == ["1"] or result.citations  # cited
        assert result.trace.tools_invoked == []

    def test_B_pure_tool(self) -> None:
        service = _service(
            translator=_translator("job_description_analysis", retrieval_required=True),
            synth_text="Tool results (calculated): role requirements extracted.",
        )
        result = service.answer(
            "Analyse this job description.",
            job_description="Senior Data Engineer needing Python, SQL and AWS.",
        )
        assert result.trace.rag_required is False  # route says no RAG for JD analysis
        assert result.retrieved == []
        names = [te.tool_name for te in result.tool_calls]
        assert names == [constants.TOOL_JOB_ANALYZER]
        assert result.tool_calls[0].status == "ok"

    def test_C_rag_plus_tool(self) -> None:
        service = _service(
            translator=_translator("candidate_comparison", rewritten="skills becoming important labour market AI"),
            synth_text="Evidence (from sources): AI demand rising [1]. Tool results (calculated): gap computed.",
        )
        result = service.answer(
            "Compare my background with this role and which skills matter more.",
            job_description="Data Engineer: Python, SQL, AWS.",
            candidate_background="Python and SQL engineer.",
        )
        names = [te.tool_name for te in result.tool_calls]
        assert constants.TOOL_JOB_ANALYZER in names
        assert constants.TOOL_GAP_ANALYZER in names
        assert result.trace.rag_used is True
        assert result.citations  # grounded evidence cited

    def test_D_multiple_tools(self) -> None:
        service = _service(
            translator=_translator("preparation_planning", rewritten="AI skills labour market"),
            synth_text="Recommendation: follow the plan.",
        )
        result = service.answer(
            "Build me a preparation plan for this role.",
            job_description="Data Engineer: Python, SQL, AWS.",
            candidate_background="Python developer only.",
            days_until_interview=14,
            hours_per_week=6,
        )
        names = [te.tool_name for te in result.tool_calls if te.status == "ok"]
        assert constants.TOOL_JOB_ANALYZER in names
        assert constants.TOOL_GAP_ANALYZER in names
        assert constants.TOOL_PREP_PLANNER in names

    def test_E_insufficient_evidence(self) -> None:
        service = _service(
            store=_empty_store(),
            translator=_translator("skill_research"),
            synth_text=constants.INSUFFICIENT_EVIDENCE_MESSAGE,
        )
        result = service.answer("What does the evidence say about quantum HR?")
        assert result.trace.rag_used is False
        assert result.answer == constants.INSUFFICIENT_EVIDENCE_MESSAGE
        assert result.citations == []
        assert any("No evidence" in n for n in result.trace.notes)

    def test_F_translation_failure_falls_back(self) -> None:
        service = _service(translator=_translator("skill_research", raises=True), synth_text="Answer.")
        result = service.answer("ambiguous question about skills")
        assert "translation" in result.trace.degraded
        assert result.answer == "Answer."  # pipeline still completes

    def test_G_tool_failure_is_contained(self) -> None:
        def boom(messages):
            raise RuntimeError("leaky secret detail")

        service = _service(
            translator=_translator("job_description_analysis", retrieval_required=False),
            invoker=_invoker(job_producer=boom),
            synth_text="Limited answer.",
        )
        result = service.answer("Analyse this JD.", job_description="Some JD text.")
        assert result.tool_calls[0].status == "error"
        assert "leaky secret detail" not in (result.tool_calls[0].error or "")
        assert constants.TOOL_JOB_ANALYZER in result.trace.degraded
        assert result.answer  # no crash

    def test_H_empty_vector_db(self) -> None:
        service = _service(store=_empty_store(), synth_text="No evidence available.")
        result = service.answer("What is the evidence on AI skills?")
        assert result.retrieved == []
        assert result.trace.rag_used is False

    def test_I_hybrid_degradation(self) -> None:
        class BoomKeyword:
            def retrieve(self, *args, **kwargs):
                raise RuntimeError("bm25 down")

        store = _corpus_store()
        retriever = HybridRetriever(VectorRetriever(store), BoomKeyword())
        service = _service(
            retriever=retriever,
            translator=_translator("skill_research", rewritten="AI machine learning labour market"),
            synth_text="Evidence [1].",
        )
        result = service.answer("AI skills evidence?")
        assert "keyword" in result.trace.degraded
        assert result.trace.rag_used is True  # vector channel still worked

    def test_J_invalid_structured_output(self) -> None:
        def bad_structure(messages):
            return "this is not a RoleRequirements object"

        service = _service(
            translator=_translator("job_description_analysis", retrieval_required=False),
            invoker=_invoker(job_producer=bad_structure),
            synth_text="Answer.",
        )
        result = service.answer("Analyse this JD.", job_description="JD text.")
        assert result.tool_calls[0].status == "error"
        assert result.answer  # contained, no crash
