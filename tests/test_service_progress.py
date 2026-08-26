"""Phase 10R tests: Career progress states + starter prompts (offline)."""

import json

from src.copilot.config import CopilotConfig
from src.copilot.embeddings import LocalHashEmbedder
from src.copilot.models import DocumentChunk
from src.copilot.rag.responder import ModelReply
from src.copilot.rag.translation import QueryTranslator
from src.copilot.retrieval import build_retriever
from src.copilot.service import CareerIntelligenceService
from src.copilot.tools import ToolInvoker, build_tool_registry
from src.copilot.tools.schemas import RoleRequirements
from src.copilot.vectorstore import InMemoryVectorStore

CONFIG = CopilotConfig()


def _store():
    s = InMemoryVectorStore(LocalHashEmbedder())
    s.add_chunks([DocumentChunk(chunk_id="a", doc_id="d", text="AI skills demand rises.", metadata={"title": "AI"})])
    return s


def _translator(intent, rewritten="AI skills demand"):
    payload = {
        "intent": intent, "retrieval_required": True, "rewritten_query": rewritten,
        "alternate_queries": [], "metadata_filters": {}, "explanation": "ok",
    }
    return QueryTranslator(responder=lambda m: ModelReply(content=json.dumps(payload)))


def _service(translator):
    return CareerIntelligenceService(
        config=CONFIG,
        retriever=build_retriever(CONFIG, mode="hybrid", store=_store()),
        translator=translator,
        tool_invoker=ToolInvoker(
            build_tool_registry(config=None, job_producer=lambda m: RoleRequirements(role_title="DE"))
        ),
        synthesis_responder=lambda m: ModelReply(content="AI skills matter [1]."),
    )


class TestProgress:
    def test_progress_states_for_pure_rag(self) -> None:
        steps: list[str] = []
        _service(_translator("skill_research")).answer(
            "What skills matter?", progress=steps.append
        )
        # Ordered subset of the documented Career progress states.
        assert steps[0] == "Understanding request"
        assert "Translating query" in steps
        assert "Searching knowledge base" in steps
        assert "Combining results" in steps
        assert steps[-1] == "Preparing response"
        assert "Running tools" not in steps  # no tools for pure RAG

    def test_progress_includes_running_tools_when_tools_used(self) -> None:
        steps: list[str] = []
        _service(_translator("job_description_analysis")).answer(
            "Analyse this JD.", job_description="Data Engineer: Python.", progress=steps.append
        )
        assert "Running tools" in steps

    def test_progress_is_optional(self) -> None:
        # No callback -> no error.
        result = _service(_translator("skill_research")).answer("What skills matter?")
        assert result.answer


class TestStarterPrompts:
    def test_starter_prompts_present(self) -> None:
        from src.career.ui import STARTER_PROMPTS

        assert "Analyse this job description." in STARTER_PROMPTS
        assert any("30-day" in p for p in STARTER_PROMPTS)
        assert len(STARTER_PROMPTS) >= 6
