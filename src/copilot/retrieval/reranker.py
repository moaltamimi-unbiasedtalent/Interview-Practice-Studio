"""Optional reranking stage: vector/BM25 → RRF candidates → reranker → top-k.

Default is :class:`NoOpReranker` (returns the RRF order unchanged); CI always
uses ``none``. An optional :class:`LLMReranker` sits behind explicit provider
config. A reranker failure must never change results destructively — it returns
the original candidate order. Only safe, non-reasoning signals are recorded.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.copilot.models import RetrievalResult

__all__ = ["RerankOutcome", "BaseReranker", "NoOpReranker", "LLMReranker", "build_reranker"]


@dataclass
class RerankOutcome:
    """Reranked results plus a safe, inspector-facing trace (no model reasoning)."""

    results: list[RetrievalResult]
    reranker_used: bool = False
    reranker_provider: str = "none"
    reranked_count: int = 0
    reranker_latency_ms: float = 0.0
    notes: list[str] = field(default_factory=list)


class BaseReranker(ABC):
    """Reorders RRF candidates. Implementations must be side-effect free."""

    provider: str = "abstract"

    @abstractmethod
    def _rerank(self, query: str, candidates: list[RetrievalResult]) -> list[RetrievalResult]:
        ...

    def rerank(self, query: str, candidates: list[RetrievalResult], *,
               top_k: int) -> RerankOutcome:
        started = time.perf_counter()
        if not candidates:
            return RerankOutcome(results=[], reranker_provider=self.provider)
        try:
            ordered = self._rerank(query, list(candidates))
        except Exception as exc:  # noqa: BLE001 - failure returns original order
            return RerankOutcome(
                results=candidates[:top_k], reranker_used=False,
                reranker_provider=self.provider,
                reranker_latency_ms=round((time.perf_counter() - started) * 1000, 2),
                notes=[f"Reranker failed ({type(exc).__name__}); kept RRF order."])
        return RerankOutcome(
            results=ordered[:top_k], reranker_used=(self.provider != "none"),
            reranker_provider=self.provider, reranked_count=len(candidates),
            reranker_latency_ms=round((time.perf_counter() - started) * 1000, 2))


class NoOpReranker(BaseReranker):
    """Keeps the RRF order (default). No model, no cost."""

    provider = "none"

    def _rerank(self, query, candidates):
        return candidates


class LLMReranker(BaseReranker):
    """Reorder candidates with the chat model scoring query–passage relevance.

    Behind explicit config only; never used in CI. Requires a responder (injected
    for tests / built from config in production). On any error the base class
    returns the original RRF order.
    """

    provider = "llm"

    def __init__(self, responder=None, config=None) -> None:
        self._responder = responder
        self._config = config

    def _get_responder(self):
        if self._responder is not None:
            return self._responder
        from src.copilot.rag.responder import build_openrouter_responder
        # Small deterministic scoring call.
        return build_openrouter_responder(self._config, max_tokens=256, temperature=0.0)

    def _rerank(self, query, candidates):
        import json
        responder = self._get_responder()
        listing = "\n".join(f"[{i}] {c.title or 'source'}: {c.text[:200]}"
                            for i, c in enumerate(candidates))
        messages = [
            {"role": "system", "content":
             "You rank passages by relevance to the question. Reply with ONLY a JSON "
             "array of passage indices, most relevant first. No prose."},
            {"role": "user", "content": f"Question: {query}\n\nPassages:\n{listing}"},
        ]
        reply = responder(messages)
        order = json.loads((reply.content or "").strip())
        seen, ordered = set(), []
        for idx in order:
            if isinstance(idx, int) and 0 <= idx < len(candidates) and idx not in seen:
                seen.add(idx); ordered.append(candidates[idx])
        # Append any not mentioned, preserving RRF order (never drop candidates).
        for i, c in enumerate(candidates):
            if i not in seen:
                ordered.append(c)
        return ordered


def build_reranker(config=None, *, responder=None) -> BaseReranker:
    """Build the configured reranker; defaults to NoOp (no provider / CI)."""
    provider = (getattr(config, "reranker_provider", "none") or "none").lower()
    if provider == "llm":
        return LLMReranker(responder=responder, config=config)
    return NoOpReranker()
