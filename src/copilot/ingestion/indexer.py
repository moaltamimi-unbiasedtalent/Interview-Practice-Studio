"""Ingestion orchestration: discover → load → clean → chunk → dedup → report.

No embeddings are created here. The indexer produces :class:`DocumentChunk`s and
a statistics report, and can persist processed chunks + a manifest so the UI and
later phases can read the knowledge base without re-ingesting.
"""

from __future__ import annotations

import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field

from src.copilot import constants
from src.copilot.ingestion import loaders
from src.copilot.ingestion.chunking import chunk_units, source_id_for_bytes
from src.copilot.models import DocumentChunk

__all__ = [
    "IngestionReport",
    "discover_documents",
    "ingest_paths",
    "ingest_directory",
    "write_processed",
    "load_manifest",
]


@dataclass
class IngestionReport:
    """Statistics from an ingestion run (safe to display; no raw content)."""

    documents: int = 0
    chunks: int = 0
    skipped_duplicate_files: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    filenames: list[str] = field(default_factory=list)
    per_document: list[dict] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


def discover_documents(raw_dir: str = constants.RAW_DIR) -> list[str]:
    """Return supported source files under ``raw_dir`` (recursive), sorted.

    Skips the README and placeholder files.
    """
    found: list[str] = []
    for root, _dirs, files in os.walk(raw_dir):
        for name in files:
            if name.lower() == "readme.md" or name == ".gitkeep":
                continue
            if name.endswith(".meta.json"):
                continue
            if os.path.splitext(name)[1].lower() in constants.SUPPORTED_EXTENSIONS:
                found.append(os.path.join(root, name))
    return sorted(found)


def ingest_paths(
    paths: Sequence[str],
    *,
    content_columns: list[str] | None = None,
    metadata_columns: list[str] | None = None,
    chunk_size: int = constants.CHUNK_SIZE,
    chunk_overlap: int = constants.CHUNK_OVERLAP,
    chunking_strategy: str = constants.DEFAULT_CHUNKING_STRATEGY,
) -> tuple[list[DocumentChunk], IngestionReport]:
    """Ingest specific files. Identical files (same bytes) are ingested once."""
    report = IngestionReport()
    all_chunks: list[DocumentChunk] = []
    seen_source_ids: set[str] = set()

    for path in paths:
        filename = os.path.basename(path)
        try:
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError as exc:
            report.errors.append({"filename": filename, "error": type(exc).__name__})
            continue

        source_id = source_id_for_bytes(data)
        if source_id in seen_source_ids:
            report.skipped_duplicate_files += 1
            continue

        try:
            units = loaders.load_document(
                path,
                content_columns=content_columns,
                metadata_columns=metadata_columns,
            )
        except loaders.LoaderError as exc:
            report.errors.append({"filename": filename, "error": str(exc)})
            continue

        chunks = chunk_units(
            units,
            source_id=source_id,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            strategy=chunking_strategy,
        )
        if not chunks:
            # Empty/blank document: recorded but contributes no chunks.
            report.per_document.append(
                {
                    "source_id": source_id,
                    "filename": filename,
                    "document_type": loaders.document_type_for_path(path),
                    "title": os.path.splitext(filename)[0],
                    "chunks": 0,
                }
            )
            report.filenames.append(filename)
            report.documents += 1
            seen_source_ids.add(source_id)
            continue

        seen_source_ids.add(source_id)
        all_chunks.extend(chunks)
        doc_type = chunks[0].metadata.get("document_type", constants.DEFAULT_DOCUMENT_TYPE)
        report.documents += 1
        report.chunks += len(chunks)
        report.by_type[doc_type] = report.by_type.get(doc_type, 0) + 1
        report.filenames.append(filename)
        report.per_document.append(
            {
                "source_id": source_id,
                "filename": filename,
                "document_type": doc_type,
                "title": chunks[0].metadata.get("title", filename),
                "chunks": len(chunks),
            }
        )
    return all_chunks, report


def ingest_directory(
    raw_dir: str = constants.RAW_DIR, **kwargs
) -> tuple[list[DocumentChunk], IngestionReport]:
    """Discover and ingest every supported document under ``raw_dir``."""
    return ingest_paths(discover_documents(raw_dir), **kwargs)


def write_processed(
    chunks: Sequence[DocumentChunk],
    report: IngestionReport,
    *,
    chunks_path: str = constants.PROCESSED_CHUNKS_FILE,
    manifest_path: str = constants.PROCESSED_MANIFEST_FILE,
) -> None:
    """Persist processed chunks (JSONL) and a manifest (JSON). No embeddings."""
    os.makedirs(os.path.dirname(chunks_path) or ".", exist_ok=True)
    with open(chunks_path, "w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(report.as_dict(), handle, indent=2, ensure_ascii=False)


def load_manifest(manifest_path: str = constants.PROCESSED_MANIFEST_FILE) -> dict | None:
    """Load a previously written manifest for display, or None if absent."""
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
