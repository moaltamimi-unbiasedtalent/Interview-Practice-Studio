"""Typed domain models for Career Intelligence Copilot.

Kept intentionally small in Phase 1 — enough to describe documents, retrieval,
query translation, tool calls, citations, chat responses and usage. Fields will
grow as RAG and tools are built. Validation happens at the edges so the rest of
the app can trust its data.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.copilot import constants

__all__ = [
    "SourceDocument",
    "DocumentChunk",
    "RetrievalResult",
    "TranslatedQuery",
    "ToolExecution",
    "Citation",
    "ChatResponse",
    "UsageRecord",
]


class _Base(BaseModel):
    """Shared config: trim strings; reject unknown keys on inputs by default."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class SourceDocument(_Base):
    """A source document ingested into the knowledge base."""

    doc_id: str = Field(description="Stable identifier for the source document.")
    title: str | None = Field(default=None, description="Human-readable title.")
    source: str = Field(description="Origin (file path, URL or dataset name).")
    doc_type: str | None = Field(
        default=None, description="Category, e.g. role_profile, interview_guide."
    )
    metadata: dict = Field(default_factory=dict, description="Free-form metadata.")


class DocumentChunk(_Base):
    """A retrievable chunk of a source document."""

    chunk_id: str = Field(description="Stable identifier for the chunk.")
    doc_id: str = Field(description="Parent source document id.")
    text: str = Field(min_length=1, description="Chunk text.")
    position: int = Field(default=0, ge=0, description="Order within the document.")
    metadata: dict = Field(default_factory=dict, description="Chunk-level metadata.")


class RetrievalResult(_Base):
    """One retrieved chunk with its relevance score and provenance."""

    chunk: DocumentChunk
    score: float = Field(description="Relevance score (higher is better).")
    retriever: str = Field(
        default="vector", description="Which retriever surfaced it (vector/keyword/hybrid)."
    )


class TranslatedQuery(_Base):
    """The output of query translation (rewrites/expansions of the user query)."""

    original: str = Field(min_length=1, description="The user's original query.")
    rewrites: list[str] = Field(
        default_factory=list, description="Rewritten/expanded query variants."
    )
    strategy: str = Field(
        default="passthrough",
        description="Translation strategy used (multi_query, hyde, decompose, …).",
    )


class ToolExecution(_Base):
    """A record of a tool call and its result, for UI visibility."""

    tool_name: str = Field(description="Registered tool name that was called.")
    arguments: dict = Field(default_factory=dict, description="Validated arguments.")
    result: dict | None = Field(default=None, description="Structured tool result.")
    ok: bool = Field(default=True, description="Whether the tool succeeded.")
    error: str | None = Field(default=None, description="Safe error message if failed.")


class Citation(_Base):
    """A citation linking an answer claim to a source chunk."""

    marker: str = Field(description="In-text marker, e.g. [1].")
    doc_id: str = Field(description="Cited source document id.")
    chunk_id: str = Field(description="Cited chunk id.")
    title: str | None = Field(default=None, description="Source title for display.")
    source: str | None = Field(default=None, description="Source path/URL for display.")


class UsageRecord(_Base):
    """Token usage and cost for one model request (kept separate per call)."""

    model: str = Field(description="Model that produced the response.")
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0, description="USD, if known.")
    currency: str = Field(default=constants.DEFAULT_CURRENCY)


class ChatResponse(_Base):
    """A grounded assistant response with its evidence and instrumentation."""

    answer: str = Field(description="The assistant's answer text.")
    citations: list[Citation] = Field(default_factory=list)
    retrieved: list[RetrievalResult] = Field(default_factory=list)
    tool_calls: list[ToolExecution] = Field(default_factory=list)
    translated_query: TranslatedQuery | None = Field(default=None)
    usage: UsageRecord | None = Field(default=None)
