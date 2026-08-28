"""Context builder + citation mapping for the RAG chain.

Turns ranked retrieval results into a single numbered context string (bounded by
a character budget) and a parallel list of :class:`Citation`s whose markers map
one-to-one to the numbered passages. This is what guarantees that every citation
the model can emit corresponds to a real retrieved chunk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.copilot import constants
from src.copilot.models import Citation, RetrievalResult

__all__ = ["ContextBundle", "build_context"]


@dataclass
class ContextBundle:
    """The assembled context plus the citations and results actually used."""

    context_text: str = ""
    citations: list[Citation] = field(default_factory=list)
    used: list[RetrievalResult] = field(default_factory=list)

    @property
    def has_context(self) -> bool:
        return bool(self.used)


def _passage_header(marker: str, result: RetrievalResult) -> str:
    title = result.title or "Untitled source"
    page = result.page
    if page is not None:
        return f"{marker} {title} (page {page})"
    return f"{marker} {title}"


def _source_url(result: RetrievalResult) -> str | None:
    """Resolve a public source URL for a retrieved chunk, if known.

    Prefers an explicit ``source_url`` on the chunk metadata (set via ingestion
    sidecar); otherwise resolves a manifest ``source_id`` to its catalogue URL so
    citations link back to the authoritative source.
    """
    meta = result.metadata or {}
    url = meta.get("source_url")
    if url:
        return url
    try:
        from src.copilot.knowledge.manifest import url_for_source

        return url_for_source(meta.get("manifest_source_id") or meta.get("source_id"))
    except Exception:  # pragma: no cover - manifest optional
        return None


def build_context(
    results: list[RetrievalResult],
    *,
    max_chars: int = constants.MAX_CONTEXT_CHARS,
) -> ContextBundle:
    """Build a numbered context string and matching citations within a budget.

    Passages are added in rank order until the character budget is reached. Each
    included passage gets a ``[n]`` marker and a matching :class:`Citation`, so
    markers always map to real retrieved chunks.
    """
    bundle = ContextBundle()
    used_chars = 0
    for index, result in enumerate(results, start=1):
        marker = f"[{index}]"
        header = _passage_header(marker, result)
        block = f"{header}\n{result.text.strip()}\n"
        # Always include the first passage even if it alone exceeds the budget
        # (truncated), so a single long chunk still grounds the answer.
        if bundle.used and used_chars + len(block) > max_chars:
            break
        if not bundle.used and len(block) > max_chars:
            block = block[:max_chars]
        bundle.context_text += block + "\n"
        used_chars += len(block) + 1
        bundle.used.append(result)
        bundle.citations.append(
            Citation(
                marker=marker,
                doc_id=result.chunk.doc_id,
                chunk_id=result.chunk.chunk_id,
                title=result.title,
                source=result.source,
                source_url=_source_url(result),
                page=result.page,
            )
        )
    bundle.context_text = bundle.context_text.strip()
    return bundle
