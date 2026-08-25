"""Baseline vector RAG chain.

Pipeline:

    query -> vector retrieval -> context builder -> domain system prompt
          -> OpenRouter (LangChain) -> grounded answer + citations

The chain is decoupled from the model behind a ``responder`` callable so tests
can inject a fake and never hit the network. The default responder uses the
LangChain OpenRouter chat model. Only citations whose markers actually appear in
the answer are returned, so displayed citations always map to real cited chunks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.models import (
    ChatResponse,
    Citation,
    RetrievalResult,
    TranslatedQuery,
    UsageRecord,
)
from src.copilot.rag.context import ContextBundle, build_context
from src.copilot.rag.prompts import build_messages
from src.copilot.retrieval.vector import VectorRetriever

__all__ = ["RagChain", "RagChainError", "ModelReply", "Responder"]

_MARKER_RE = re.compile(r"\[(\d+)\]")


class RagChainError(Exception):
    """Raised when the chain cannot run (e.g. no model configured)."""


@dataclass
class ModelReply:
    """A uniform model reply the chain understands (content + optional usage)."""

    content: str
    usage: UsageRecord | None = None


#: A responder turns assembled messages into a :class:`ModelReply`.
Responder = Callable[[list[dict]], ModelReply]


def _referenced_markers(answer: str) -> set[str]:
    return {f"[{n}]" for n in _MARKER_RE.findall(answer)}


def _usage_from_lc(message: Any, model: str) -> UsageRecord | None:
    """Extract token usage from a LangChain AIMessage, if present."""
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return UsageRecord(
            model=model,
            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
        )
    return None


def _openrouter_responder(
    config: CopilotConfig,
    *,
    model: str | None,
    temperature: float | None,
    max_tokens: int | None,
) -> Responder:
    """Build a responder backed by the LangChain OpenRouter chat model."""
    from src.copilot.llm.openrouter import CopilotConfigError, build_chat_model

    try:
        chat_model = build_chat_model(
            config, model=model, temperature=temperature, max_tokens=max_tokens
        )
    except CopilotConfigError as exc:
        raise RagChainError(str(exc)) from exc

    resolved_model = model or config.default_model
    role_map = {"system": "system", "user": "human", "assistant": "ai"}

    def respond(messages: list[dict]) -> ModelReply:
        lc_messages = [(role_map.get(m["role"], "human"), m["content"]) for m in messages]
        result = chat_model.invoke(lc_messages)
        content = getattr(result, "content", "") or ""
        return ModelReply(content=content, usage=_usage_from_lc(result, resolved_model))

    return respond


class RagChain:
    """Baseline retrieval-augmented chat over the career knowledge base."""

    def __init__(
        self,
        retriever: VectorRetriever,
        *,
        config: CopilotConfig | None = None,
        responder: Responder | None = None,
        top_k: int = constants.DEFAULT_TOP_K,
        max_context_chars: int = constants.MAX_CONTEXT_CHARS,
    ) -> None:
        self.retriever = retriever
        self.config = config
        self._responder = responder
        self.top_k = top_k
        self.max_context_chars = max_context_chars

    def _get_responder(
        self, *, model: str | None, temperature: float | None, max_tokens: int | None
    ) -> Responder:
        if self._responder is not None:
            return self._responder
        if self.config is None:
            raise RagChainError("RagChain needs a responder or a config to call a model.")
        return _openrouter_responder(
            self.config, model=model, temperature=temperature, max_tokens=max_tokens
        )

    def retrieve(
        self, query: str, *, filters: dict | None = None
    ) -> list[RetrievalResult]:
        return self.retriever.retrieve(query, top_k=self.top_k, filters=filters)

    def answer(
        self,
        query: str,
        *,
        filters: dict | None = None,
        results: list[RetrievalResult] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Run the full RAG pipeline and return a grounded :class:`ChatResponse`.

        ``results`` may be supplied to reuse an earlier retrieval (e.g. so the UI
        can show retrieval progress) instead of retrieving again.
        """
        query = (query or "").strip()
        if not query:
            raise RagChainError("Query must not be empty.")

        if results is None:
            results = self.retrieve(query, filters=filters)
        bundle: ContextBundle = build_context(results, max_chars=self.max_context_chars)
        messages = build_messages(query, bundle.context_text)

        responder = self._get_responder(
            model=model, temperature=temperature, max_tokens=max_tokens
        )
        reply = responder(messages)

        citations = _select_citations(reply.content, bundle.citations)
        return ChatResponse(
            answer=reply.content,
            citations=citations,
            retrieved=results,
            translated_query=TranslatedQuery(original=query, strategy="passthrough"),
            usage=reply.usage,
        )


def _select_citations(answer: str, available: list[Citation]) -> list[Citation]:
    """Return only the citations whose markers appear in the answer text."""
    referenced = _referenced_markers(answer)
    return [c for c in available if c.marker in referenced]
