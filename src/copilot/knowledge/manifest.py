"""Source manifest: the register of every configured knowledge source.

Loads ``data/source_manifest.json`` into typed :class:`SourceEntry` records.
Licence terms are never invented — uncertain ones are flagged
``licence_review_required``; sources that cannot be auto-downloaded are flagged
``manual_acquisition_required``.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, ConfigDict, Field

from src.copilot import constants

__all__ = ["SourceEntry", "load_manifest", "by_type", "auto_downloadable", "manual_sources"]


class SourceEntry(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    source_id: str
    title: str
    publisher: str
    authority: str | None = None
    authority_level: int = Field(default=constants.AUTHORITY_INDUSTRY, ge=1, le=3)
    country: str | None = None
    language: str | None = None
    source_type: str = "industry_report"
    version: str | None = None
    reference_year: int | None = None
    licence: str | None = None
    licence_notes: str | None = None
    source_url: str | None = None
    download_url: str | None = None
    retrieval_date: str | None = None
    storage_target: str | None = None  # structured_role | vector | compensation
    ingestion_method: str | None = None
    refresh_frequency: str | None = None
    redistribution_allowed: bool = False
    manual_acquisition_required: bool = False
    licence_review_required: bool = False
    manual_review_required: bool = False


def load_manifest(path: str = constants.SOURCE_MANIFEST_PATH) -> list[SourceEntry]:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    entries = data.get("sources", data) if isinstance(data, dict) else data
    return [SourceEntry(**entry) for entry in entries]


def by_type(entries: list[SourceEntry], source_type: str) -> list[SourceEntry]:
    return [e for e in entries if e.source_type == source_type]


def auto_downloadable(entries: list[SourceEntry]) -> list[SourceEntry]:
    """Sources safe to auto-download: a direct URL and no manual/licence block."""
    return [
        e
        for e in entries
        if e.download_url
        and not e.manual_acquisition_required
        and not e.licence_review_required
    ]


def manual_sources(entries: list[SourceEntry]) -> list[SourceEntry]:
    return [e for e in entries if e.manual_acquisition_required]
