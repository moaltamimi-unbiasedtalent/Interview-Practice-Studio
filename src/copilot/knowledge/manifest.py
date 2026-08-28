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

__all__ = [
    "SourceEntry", "load_manifest", "by_type", "by_group", "auto_downloadable",
    "manual_sources", "url_for_source", "GROUPS",
]

# UI grouping order for the Knowledge Base page.
GROUPS = [
    ("occupations", "Occupations & Role Data"),
    ("skills", "Skills & Competencies"),
    ("job_architecture", "Seniority & Job Architecture"),
    ("compensation", "Compensation"),
    ("labour_market", "Labour Market & Forecasts"),
    ("narrative", "Narrative / Methodology"),
    ("specialist", "Specialist Profession Packs"),
]


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
    version_policy: str | None = None  # e.g. "detect-at-acquisition" | "pinned"
    reference_year: int | None = None
    region: str | None = None
    publication_date: str | None = None
    licence: str | None = None
    licence_notes: str | None = None
    source_url: str | None = None
    download_url: str | None = None
    retrieval_date: str | None = None
    storage_target: str | None = None  # structured_role | compensation | labour_market | competency | vector
    ingestion_method: str | None = None
    refresh_frequency: str | None = None
    group: str | None = None  # UI section: occupations | skills | job_architecture | compensation | labour_market | narrative | specialist
    coverage_areas: list[str] = Field(default_factory=list)
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


def by_group(entries: list[SourceEntry], group: str) -> list[SourceEntry]:
    return [e for e in entries if e.group == group]


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


# Cache the id → URL map so per-citation lookups don't reload the manifest.
_URL_BY_SOURCE: dict[str, str] | None = None


def url_for_source(source_id: str | None,
                   path: str = constants.SOURCE_MANIFEST_PATH) -> str | None:
    """Return the public source URL for a manifest ``source_id`` (or None).

    Used to turn a retrieved chunk's provenance into a clickable citation link.
    """
    global _URL_BY_SOURCE
    if not source_id:
        return None
    if _URL_BY_SOURCE is None:
        try:
            _URL_BY_SOURCE = {
                e.source_id: e.source_url for e in load_manifest(path) if e.source_url
            }
        except Exception:  # pragma: no cover - manifest optional/malformed
            _URL_BY_SOURCE = {}
    return _URL_BY_SOURCE.get(source_id)
