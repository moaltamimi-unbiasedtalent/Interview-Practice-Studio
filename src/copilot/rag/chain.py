"""Advanced vector RAG chain.

Pipeline:

    query -> query translation (intent, rewrite, multi-query, safe filters)
          -> vector retrieval per query -> reciprocal-rank fusion
          -> context builder -> domain system prompt
          -> OpenRouter (LangChain) -> grounded answer + citations

Translation is optional (inject a :class:`~src.copilot.rag.translation.QueryTranslator`);
without one the chain falls back to a passthrough that retrieves for the original
query. The model sits behind a ``responder`` callable so tests never hit the
network. Only citations whose markers appear in the answer are returned.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.models import ChatResponse, Citation, RetrievalResult, TranslatedQuery
from src.copilot.rag.context import ContextBundle, build_context
from src.copilot.rag.prompts import build_messages
from src.copilot.rag.responder import ModelReply, Responder, build_openrouter_responder
from src.copilot.retrieval.fusion import reciprocal_rank_fusion
from src.copilot.retrieval.vector import VectorRetriever

if TYPE_CHECKING:  # avoid a runtime import cycle (translation imports responder)
    from src.copilot.rag.translation import QueryTranslator

__all__ = ["RagChain", "RagChainError", "ModelReply", "Responder"]

_MARKER_RE = re.compile(r"\[(\d+)\]")


class RagChainError(Exception):
    """Raised when the chain cannot run (e.g. no model configured)."""


def _referenced_markers(answer: str) -> set[str]:
    return {f"[{n}]" for n in _MARKER_RE.findall(answer)}


def _select_citations(answer: str, available: list[Citation]) -> list[Citation]:
    """Return only the citations whose markers appear in the answer text."""
    referenced = _referenced_markers(answer)
    return [c for c in available if c.marker in referenced]


class RagChain:
    """Retrieval-augmented chat over the career knowledge base."""

    def __init__(
        self,
        retriever: VectorRetriever,
        *,
        config: CopilotConfig | None = None,
        responder: Responder | None = None,
        translator: "QueryTranslator | None" = None,
        top_k: int = constants.DEFAULT_TOP_K,
        max_context_chars: int = constants.MAX_CONTEXT_CHARS,
    ) -> None:
        self.retriever = retriever
        self.config = config
        self._responder = responder
        self.translator = translator
        self.top_k = top_k
        self.max_context_chars = max_context_chars

    # -- model -------------------------------------------------------------

    def _get_responder(
        self, *, model: str | None, temperature: float | None, max_tokens: int | None
    ) -> Responder:
        if self._responder is not None:
            return self._responder
        if self.config is None:
            raise RagChainError("RagChain needs a responder or a config to call a model.")
        return build_openrouter_responder(
            self.config, model=model, temperature=temperature, max_tokens=max_tokens
        )

    # -- translation + retrieval ------------------------------------------

    def translate(self, query: str, *, filters: dict | None = None) -> TranslatedQuery:
        """Translate the query, or build a passthrough when no translator is set.

        Caller-supplied ``filters`` are merged over any the translator inferred.
        """
        if self.translator is not None:
            translated = self.translator.translate(query)
        else:
            translated = TranslatedQuery(
                original_query=query,
                rewritten_query=query,
                strategy="passthrough",
            )
        if filters:
            merged = dict(translated.metadata_filters)
            merged.update(filters)
            translated = translated.model_copy(update={"metadata_filters": merged})
        return translated

    def retrieve(
        self, query: str, *, filters: dict | None = None
    ) -> list[RetrievalResult]:
        """Single-query retrieval (no translation). Used by the UI/tests."""
        return self.retriever.retrieve(query, top_k=self.top_k, filters=filters)

    def retrieve_translated(self, translated: TranslatedQuery) -> list[RetrievalResult]:
        """Retrieve for every translated query and fuse with reciprocal rank."""
        if not translated.retrieval_required:
            return []
        filters = translated.metadata_filters or None
        ranked_lists = [
            self.retriever.retrieve(query, top_k=self.top_k, filters=filters)
            for query in translated.all_queries
        ]
        return reciprocal_rank_fusion(ranked_lists, top_k=self.top_k)

    # -- full pipeline -----------------------------------------------------

    def answer(
        self,
        query: str,
        *,
        filters: dict | None = None,
        translated: TranslatedQuery | None = None,
        results: list[RetrievalResult] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResponse:
        """Run the full RAG pipeline and return a grounded :class:`ChatResponse`.

        ``translated`` and/or ``results`` may be supplied to reuse work already
        done (e.g. so the UI can show translation/retrieval progress) instead of
        recomputing.
        """
        query = (query or "").strip()
        if not query:
            raise RagChainError("Query must not be empty.")

        if translated is None:
            translated = self.translate(query, filters=filters)
        if results is None:
            results = self.retrieve_translated(translated)

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
            translated_query=translated,
            usage=reply.usage,
        )
