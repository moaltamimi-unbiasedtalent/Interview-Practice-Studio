"""Foundation tests for Career Intelligence Copilot domain models."""

import pytest
from pydantic import ValidationError

from src.copilot.models import (
    ChatResponse,
    Citation,
    DocumentChunk,
    RetrievalResult,
    SourceDocument,
    ToolExecution,
    TranslatedQuery,
    UsageRecord,
)


def _chunk() -> DocumentChunk:
    return DocumentChunk(chunk_id="c1", doc_id="d1", text="Nurses triage patients.")


class TestModels:
    def test_source_document_builds(self) -> None:
        doc = SourceDocument(doc_id="d1", source="data/raw/roles.md", title="Roles")
        assert doc.metadata == {}

    def test_chunk_requires_text(self) -> None:
        with pytest.raises(ValidationError):
            DocumentChunk(chunk_id="c", doc_id="d", text="")

    def test_retrieval_result_wraps_chunk(self) -> None:
        result = RetrievalResult(chunk=_chunk(), score=0.87, retriever="hybrid")
        assert result.chunk.doc_id == "d1"
        assert result.retriever == "hybrid"

    def test_translated_query_defaults(self) -> None:
        tq = TranslatedQuery(original="What skills for a nurse?")
        assert tq.rewrites == [] and tq.strategy == "passthrough"

    def test_tool_execution_records_result(self) -> None:
        te = ToolExecution(
            tool_name="job_description_analyzer",
            arguments={"text": "…"},
            result={"skills": ["triage"]},
        )
        assert te.ok is True and te.error is None

    def test_usage_record_defaults(self) -> None:
        usage = UsageRecord(model="openai/gpt-5-mini")
        assert usage.total_tokens == 0 and usage.currency == "USD"

    def test_chat_response_composes_evidence(self) -> None:
        response = ChatResponse(
            answer="Nurses need triage skills [1].",
            citations=[Citation(marker="[1]", doc_id="d1", chunk_id="c1")],
            retrieved=[RetrievalResult(chunk=_chunk(), score=0.9)],
        )
        assert response.citations[0].marker == "[1]"
        assert response.tool_calls == []

    def test_unknown_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(model="m", bogus=1)
