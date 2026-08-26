"""Source lifecycle status — the operational truth for each configured source.

Static metadata lives in ``data/source_manifest.json``; this module derives the
mutable runtime status (configured → acquisition available → acquired →
normalised → indexed → available_for_retrieval) from what is actually on disk:
the structured stores, the vector manifest, and any downloaded files. A source
appearing in the manifest is NEVER assumed to be loaded.
"""

from __future__ import annotations

import json
import os

from pydantic import BaseModel, Field

from src.copilot import constants
from src.copilot.knowledge import manifest as km

__all__ = ["SourceStatus", "compute_status", "write_status", "load_status", "summary"]

# Lifecycle badge precedence (most-advanced first).
AVAILABLE = "AVAILABLE"
INDEXED = "INDEXED"
NORMALISED = "NORMALISED"
ACQUIRED = "ACQUIRED"
MANUAL = "MANUAL ACQUISITION"
LICENCE_REVIEW = "LICENCE REVIEW"
AUTO_AVAILABLE = "AUTO DOWNLOAD AVAILABLE"
CONFIGURED = "CONFIGURED"


class SourceStatus(BaseModel):
    source_id: str
    configured: bool = True
    acquisition_available: bool = False
    acquired: bool = False
    normalised: bool = False
    indexed: bool = False
    available_for_retrieval: bool = False
    record_count: int = 0
    chunk_count: int = 0
    detected_version: str | None = None
    detected_reference_year: int | None = None
    last_refresh: str | None = None
    last_error: str | None = None
    freshness: str = "UNKNOWN"  # CURRENT | REFRESH DUE | UNKNOWN
    needs_manual_acquisition: bool = False
    needs_licence_review: bool = False
    lifecycle: str = CONFIGURED

    def as_dict(self) -> dict:
        return self.model_dump()


def _open_counts(path: str, repo_cls) -> dict[str, int]:
    if not os.path.isfile(path):
        return {}
    repo = repo_cls(path)
    try:
        return repo.counts_by_source()
    finally:
        repo.close()


def _structured_counts() -> dict[str, int]:
    """Per-source structured record counts across all structured stores."""
    from src.copilot.knowledge.compensation import CompensationRepository
    from src.copilot.knowledge.roles import RoleRepository
    from src.copilot.knowledge.structured_ext import (
        CompetencyRepository,
        LabourMarketRepository,
    )

    counts: dict[str, int] = {}
    for path, cls in [
        (constants.ROLE_DB_PATH, RoleRepository),
        (constants.COMPENSATION_DB_PATH, CompensationRepository),
        (constants.COMPETENCY_DB_PATH, CompetencyRepository),
        (constants.LABOUR_MARKET_DB_PATH, LabourMarketRepository),
    ]:
        for sid, n in _open_counts(path, cls).items():
            counts[sid] = counts.get(sid, 0) + n
    return counts


def _vector_indexed_source_ids() -> set[str]:
    """Source ids that have narrative chunks in the vector manifest, if tracked."""
    from src.copilot.ingestion import indexer

    manifest = indexer.load_manifest()
    if not manifest:
        return set()
    ids: set[str] = set()
    for doc in manifest.get("per_document", []):
        sid = doc.get("source_id") or doc.get("source")
        if sid:
            ids.add(sid)
    return ids


def compute_status(manifest_path: str = constants.SOURCE_MANIFEST_PATH) -> list[SourceStatus]:
    entries = km.load_manifest(manifest_path)
    structured = _structured_counts()
    vector_ids = _vector_indexed_source_ids()
    downloads = "data/knowledge/downloads"

    out: list[SourceStatus] = []
    for e in entries:
        record_count = structured.get(e.source_id, 0)
        chunk_count = 0  # per-source vector chunk counts are not tracked precisely
        acquired_file = os.path.isfile(os.path.join(downloads, f"{e.source_id}.bin"))
        is_narrative = e.storage_target == "vector"
        indexed = (record_count > 0) or (is_narrative and e.source_id in vector_ids)
        acquired = acquired_file or indexed
        acquisition_available = bool(
            e.download_url and not e.manual_acquisition_required and not e.licence_review_required
        )

        status = SourceStatus(
            source_id=e.source_id,
            acquisition_available=acquisition_available,
            acquired=acquired,
            normalised=record_count > 0,
            indexed=indexed,
            available_for_retrieval=indexed,
            record_count=record_count,
            chunk_count=chunk_count,
            needs_manual_acquisition=e.manual_acquisition_required,
            needs_licence_review=e.licence_review_required,
        )
        status.lifecycle = _lifecycle(status, e)
        out.append(status)
    return out


def _lifecycle(s: SourceStatus, e: km.SourceEntry) -> str:
    if s.available_for_retrieval:
        return AVAILABLE
    if s.acquired:
        return ACQUIRED
    if e.manual_acquisition_required:
        return MANUAL
    if e.licence_review_required:
        return LICENCE_REVIEW
    if s.acquisition_available:
        return AUTO_AVAILABLE
    return CONFIGURED


def write_status(path: str = constants.SOURCE_STATUS_PATH,
                 manifest_path: str = constants.SOURCE_MANIFEST_PATH) -> list[SourceStatus]:
    statuses = compute_status(manifest_path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {"generated": "on-demand", "sources": [s.as_dict() for s in statuses]}
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return statuses


def load_status(path: str = constants.SOURCE_STATUS_PATH) -> list[SourceStatus]:
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    return [SourceStatus(**s) for s in data.get("sources", [])]


def summary(statuses: list[SourceStatus]) -> dict:
    """Knowledge-health summary from a list of statuses."""
    return {
        "configured": len(statuses),
        "available_locally": sum(1 for s in statuses if s.available_for_retrieval),
        "acquired": sum(1 for s in statuses if s.acquired),
        "manual_acquisition": sum(1 for s in statuses if s.needs_manual_acquisition),
        "licence_review": sum(1 for s in statuses if s.needs_licence_review),
        "structured_records": sum(s.record_count for s in statuses),
    }
