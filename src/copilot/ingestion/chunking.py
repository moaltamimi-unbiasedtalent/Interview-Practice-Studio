"""Chunking with stable, content-derived ids for deduplication.

Uses LangChain's recursive character splitter so chunks break on natural
boundaries (paragraphs -> lines -> words). Ids are hashes of content, so
re-ingesting the same document produces the same ids and never duplicates.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from src.copilot import constants
from src.copilot.ingestion.cleaners import clean_text
from src.copilot.ingestion.loaders import LoadedUnit
from src.copilot.models import DocumentChunk

__all__ = [
    "stable_hash",
    "source_id_for_bytes",
    "source_id_for_text",
    "chunk_units",
]

_ID_SEPARATOR = "::"


def stable_hash(*parts: str) -> str:
    """A short, stable hex id derived from the given parts."""
    joined = _ID_SEPARATOR.join(parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return digest[: constants.ID_HASH_LENGTH]


def source_id_for_bytes(data: bytes) -> str:
    """Stable source id from raw file bytes (dedup identical files)."""
    return hashlib.sha256(data).hexdigest()[: constants.ID_HASH_LENGTH]


def source_id_for_text(text: str) -> str:
    return stable_hash("text", text)


def _splitter(chunk_size: int, chunk_overlap: int):
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    return RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        separators=["\n\n", "\n", ". ", " ", ""],
    )


def chunk_units(
    units: Sequence[LoadedUnit],
    *,
    source_id: str,
    chunk_size: int = constants.CHUNK_SIZE,
    chunk_overlap: int = constants.CHUNK_OVERLAP,
    strategy: str = constants.DEFAULT_CHUNKING_STRATEGY,
) -> list[DocumentChunk]:
    """Clean and split loaded units into deduplicated :class:`DocumentChunk`s.

    Chunk ids are derived from ``source_id`` + text, so identical content yields
    identical ids; duplicate chunk ids within a document are dropped.

    ``strategy``:
      * ``baseline`` — recursive character splitter (default; unchanged).
      * ``section`` — preserve each source-native unit (heading/section/page/row,
        already produced by the loaders) as a single chunk when it fits within a
        bounded section cap, splitting only over-long units. Metadata (title,
        section, page, document_type, source_id, source_url) is preserved either
        way; unstructured text with no section falls back to baseline splitting.
    """
    splitter = _splitter(chunk_size, chunk_overlap)
    # Bounded cap so "section" never emits arbitrarily giant chunks.
    section_cap = chunk_size * 4

    def _pieces(cleaned: str, unit: LoadedUnit) -> list[str]:
        if strategy == "section" and len(cleaned) <= section_cap:
            return [cleaned]  # keep the native unit intact
        return splitter.split_text(cleaned)

    chunks: list[DocumentChunk] = []
    seen: set[str] = set()
    position = 0
    for unit in units:
        cleaned = clean_text(unit.text)
        if not cleaned:
            continue
        for piece in _pieces(cleaned, unit):
            piece = piece.strip()
            if not piece:
                continue
            chunk_id = stable_hash(source_id, piece)
            if chunk_id in seen:
                continue  # exact-duplicate chunk within this document
            seen.add(chunk_id)
            metadata = dict(unit.metadata)
            metadata["source_id"] = source_id
            metadata["chunk_index"] = position
            chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    doc_id=source_id,
                    text=piece,
                    position=position,
                    metadata=metadata,
                )
            )
            position += 1
    return chunks
