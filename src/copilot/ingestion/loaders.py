"""Document loaders for the knowledge base (PDF, TXT, Markdown, CSV).

Each loader returns a list of :class:`LoadedUnit` — a piece of text with
provenance metadata (source, filename, page/section, document_type, …). Loading
does not clean or chunk; those are separate, testable stages.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from src.copilot import constants

__all__ = ["LoadedUnit", "LoaderError", "load_document", "document_type_for_path"]


class LoaderError(Exception):
    """Raised when a document cannot be loaded (malformed/unsupported)."""


@dataclass
class LoadedUnit:
    """One loaded text unit with provenance metadata (pre-clean, pre-chunk)."""

    text: str
    metadata: dict = field(default_factory=dict)


def document_type_for_path(path: str, raw_root: str | None = None) -> str:
    """Infer document_type from the immediate subfolder under the raw root."""
    directory = os.path.dirname(os.path.abspath(path))
    folder = os.path.basename(directory)
    if folder in constants.KNOWN_DOCUMENT_TYPES:
        return folder
    return constants.DEFAULT_DOCUMENT_TYPE


def _sidecar_metadata(path: str) -> dict:
    """Read optional ``<file>.meta.json`` (title/year/topic), if present."""
    sidecar = f"{path}.meta.json"
    if not os.path.isfile(sidecar):
        return {}
    try:
        with open(sidecar, encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _base_metadata(path: str, document_type: str | None) -> dict:
    filename = os.path.basename(path)
    meta = {
        "source": path,
        "filename": filename,
        "document_type": document_type or document_type_for_path(path),
        "title": os.path.splitext(filename)[0],
    }
    meta.update(_sidecar_metadata(path))  # sidecar may override title/year/topic
    return meta


def _load_pdf(path: str, base: dict) -> list[LoadedUnit]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency present in project
        raise LoaderError("pypdf is not installed.") from exc
    try:
        reader = PdfReader(path)
    except Exception as exc:  # noqa: BLE001 - malformed PDF -> controlled error
        raise LoaderError(f"Could not read PDF: {type(exc).__name__}") from exc

    pdf_title = None
    try:
        pdf_title = (reader.metadata or {}).get("/Title") if reader.metadata else None
    except Exception:  # noqa: BLE001
        pdf_title = None

    units: list[LoadedUnit] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - skip an unreadable page, keep the rest
            text = ""
        if not text.strip():
            continue
        meta = dict(base)
        meta["page"] = index
        if pdf_title:
            meta["title"] = str(pdf_title)
        units.append(LoadedUnit(text=text, metadata=meta))
    return units


def _split_markdown_sections(text: str) -> list[tuple[str | None, str]]:
    """Split markdown into (section_heading, body) parts on ATX headings."""
    sections: list[tuple[str | None, str]] = []
    current_heading: str | None = None
    buffer: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            if buffer:
                sections.append((current_heading, "\n".join(buffer).strip()))
                buffer = []
            current_heading = line.lstrip("#").strip() or None
        buffer.append(line)
    if buffer:
        sections.append((current_heading, "\n".join(buffer).strip()))
    return [(h, b) for h, b in sections if b]


def _load_text(path: str, base: dict, *, is_markdown: bool) -> list[LoadedUnit]:
    with open(path, encoding="utf-8", errors="replace") as handle:
        text = handle.read()
    if not text.strip():
        return []
    if is_markdown:
        units = []
        for heading, body in _split_markdown_sections(text):
            meta = dict(base)
            if heading:
                meta["section"] = heading
            units.append(LoadedUnit(text=body, metadata=meta))
        return units or [LoadedUnit(text=text.strip(), metadata=dict(base))]
    return [LoadedUnit(text=text.strip(), metadata=dict(base))]


def _load_csv(
    path: str,
    base: dict,
    *,
    content_columns: list[str] | None,
    metadata_columns: list[str] | None,
) -> list[LoadedUnit]:
    import pandas as pd

    try:
        frame = pd.read_csv(path, dtype=str).fillna("")
    except Exception as exc:  # noqa: BLE001 - malformed CSV -> controlled error
        raise LoaderError(f"Could not read CSV: {type(exc).__name__}") from exc
    if frame.empty:
        return []
    columns = list(frame.columns)
    content_cols = content_columns or columns  # default: use all columns
    missing = [c for c in content_cols if c not in columns]
    if missing:
        raise LoaderError(f"CSV missing content columns: {missing}")

    units: list[LoadedUnit] = []
    for row_index, row in frame.iterrows():
        parts = [f"{col}: {row[col]}" for col in content_cols if str(row[col]).strip()]
        content = "\n".join(parts).strip()
        if not content:
            continue
        meta = dict(base)
        meta["row"] = int(row_index)
        for col in metadata_columns or []:
            if col in columns:
                meta[col] = row[col]
        units.append(LoadedUnit(text=content, metadata=meta))
    return units


def load_document(
    path: str,
    *,
    document_type: str | None = None,
    content_columns: list[str] | None = None,
    metadata_columns: list[str] | None = None,
) -> list[LoadedUnit]:
    """Load one file into :class:`LoadedUnit` parts based on its extension.

    Raises :class:`LoaderError` for an unsupported or malformed file. An empty
    file yields an empty list (no units), not an error.
    """
    if not os.path.isfile(path):
        raise LoaderError(f"File not found: {path}")
    ext = os.path.splitext(path)[1].lower()
    if ext not in constants.SUPPORTED_EXTENSIONS:
        raise LoaderError(f"Unsupported file type: {ext}")

    base = _base_metadata(path, document_type)
    if ext == ".pdf":
        return _load_pdf(path, base)
    if ext in (".md", ".markdown"):
        return _load_text(path, base, is_markdown=True)
    if ext == ".txt":
        return _load_text(path, base, is_markdown=False)
    if ext == ".csv":
        return _load_csv(
            path, base, content_columns=content_columns, metadata_columns=metadata_columns
        )
    raise LoaderError(f"Unsupported file type: {ext}")  # pragma: no cover
