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
    """One retrieved chunk with its relevance score and provenance.

    Convenience accessors (``text``, ``title``, ``page``, ``source``,
    ``metadata``) read through to the underlying chunk so callers do not need to
    reach into ``chunk.metadata`` for common provenance fields.
    """

    chunk: DocumentChunk
    score: float = Field(description="Relevance score (higher is better).")
    retriever: str = Field(
        default="vector", description="Which retriever surfaced it (vector/keyword/hybrid)."
    )

    @property
    def text(self) -> str:
        return self.chunk.text

    @property
    def metadata(self) -> dict:
        return self.chunk.metadata

    @property
    def title(self) -> str | None:
        meta = self.chunk.metadata
        return meta.get("title") or meta.get("filename")

    @property
    def page(self) -> int | None:
        return self.chunk.metadata.get("page")

    @property
    def source(self) -> str | None:
        meta = self.chunk.metadata
        return meta.get("source") or meta.get("filename")


class TranslatedQuery(_Base):
    """The output of query translation (rewrites/expansions of the user query).

    Produced by the query-understanding stage before retrieval. The
    ``explanation`` is a short, user-safe rationale — never chain-of-thought.
    """

    original_query: str = Field(min_length=1, description="The user's original query.")
    rewritten_query: str = Field(
        min_length=1, description="A single clearer retrieval query (intent preserved)."
    )
    alternate_queries: list[str] = Field(
        default_factory=list,
        description="2–4 additional retrieval variants for broad questions.",
    )
    intent: str = Field(
        default="other", description="Classified query intent (see QueryIntent)."
    )
    retrieval_required: bool = Field(
        default=True, description="Whether the knowledge base should be searched."
    )
    metadata_filters: dict = Field(
        default_factory=dict,
        description="Safe, whitelisted equality filters over indexed metadata.",
    )
    explanation: str = Field(
        default="",
        description="Short, user-safe reason for the rewrite (no chain-of-thought).",
    )
    strategy: str = Field(
        default="passthrough",
        description="Translation strategy used (llm, heuristic, passthrough, fallback).",
    )

    @property
    def all_queries(self) -> list[str]:
        """Rewritten query first, then de-duplicated alternates."""
        queries = [self.rewritten_query]
        for alt in self.alternate_queries:
            if alt and alt not in queries:
                queries.append(alt)
        return queries


class ToolExecution(_Base):
    """A safe, log-friendly record of a tool call.

    Deliberately holds only *summaries* — never full candidate backgrounds or job
    descriptions — so it is safe to display and log.
    """

    tool_name: str = Field(description="Registered tool name that was called.")
    status: str = Field(
        default="ok",
        description="ok | error | invalid_args | unsupported | no_tool.",
    )
    duration_seconds: float = Field(default=0.0, ge=0)
    safe_argument_summary: str = Field(
        default="", description="Non-sensitive summary of the arguments (e.g. sizes)."
    )
    safe_result_summary: str = Field(
        default="", description="Non-sensitive summary of the result (e.g. counts)."
    )
    error: str | None = Field(default=None, description="Safe error message if failed.")

    @property
    def ok(self) -> bool:
        return self.status == "ok"


class Citation(_Base):
    """A citation linking an answer claim to a source chunk."""

    marker: str = Field(description="In-text marker, e.g. [1].")
    doc_id: str = Field(description="Cited source document id.")
    chunk_id: str = Field(description="Cited chunk id.")
    title: str | None = Field(default=None, description="Source title for display.")
    source: str | None = Field(default=None, description="Source path/URL for display.")
    page: int | None = Field(default=None, description="Page number, if known.")

    @property
    def label(self) -> str:
        """Human-readable citation line, e.g. ``[1] WEF report — page 14``."""
        title = self.title or self.source or "Untitled source"
        if self.page is not None:
            return f"{self.marker} {title} — page {self.page}"
        return f"{self.marker} {title}"


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
