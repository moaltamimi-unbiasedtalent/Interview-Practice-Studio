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
LOCAL_FILE_FOUND = "LOCAL FILE FOUND"
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
    local_files: int = 0
    local_file_found: bool = False
    last_refresh: str | None = None
    last_error: str | None = None
    freshness: str = "UNKNOWN"  # CURRENT | REFRESH DUE | UNKNOWN
    needs_manual_acquisition: bool = False
    needs_licence_review: bool = False
    # Data-origin integrity: real official data vs synthetic test fixtures.
    data_origin: str | None = None  # official_local | … | synthetic_fixture | mixed
    fixture_only: bool = False
    production_ready: bool = False
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


def _inventory_files(path: str = "data/source_inventory.json") -> dict[str, dict]:
    """Per-source local-file summary from the inventory, if it has been generated.

    Returns ``{source_id: {"files": int, "version": str|None, "year": int|None}}``
    so a configured source with real files on disk reports LOCAL FILE FOUND rather
    than implying the user still needs to acquire it manually.
    """
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict] = {}
    for f in data.get("files", []):
        sid = f.get("source_id")
        if not sid or sid == "unresolved":
            continue
        rec = out.setdefault(sid, {"files": 0, "version": None, "year": None})
        rec["files"] += 1
        rec["version"] = rec["version"] or f.get("detected_version")
        rec["year"] = rec["year"] or f.get("detected_reference_year")
    return out


def _vector_source_counts(path: str = "data/knowledge/vector_sources.json") -> dict[str, int]:
    """Measured per-source vector chunk counts written by narrative ingestion.

    Keyed by manifest ``source_id`` so a narrative source that has actually been
    indexed reports its real chunk count (rather than relying on the content-hash
    ids in the processed manifest, which do not map to manifest sources).
    """
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: int(v) for k, v in data.get("chunks_by_source", {}).items()}


def compute_status(manifest_path: str = constants.SOURCE_MANIFEST_PATH) -> list[SourceStatus]:
    from src.copilot.knowledge import origins as korigins

    entries = km.load_manifest(manifest_path)
    structured = _structured_counts()
    vector_counts = _vector_source_counts()
    inventory = _inventory_files()
    ledger = korigins.load_origins()
    downloads = "data/knowledge/downloads"

    out: list[SourceStatus] = []
    for e in entries:
        record_count = structured.get(e.source_id, 0)
        chunk_count = vector_counts.get(e.source_id, 0)
        local = inventory.get(e.source_id)
        local_files = local["files"] if local else 0
        local_file_found = local_files > 0
        acquired_file = os.path.isfile(os.path.join(downloads, f"{e.source_id}.bin"))
        # Indexed if it has structured records OR narrative chunks in the vector
        # store — a source can contribute to more than its primary lane.
        indexed = (record_count > 0) or (chunk_count > 0)
        # A raw file on disk (inventory) counts as acquired even if not yet loaded.
        acquired = acquired_file or indexed or local_file_found

        status = SourceStatus(
            source_id=e.source_id,
            acquisition_available=bool(
                e.download_url and not e.manual_acquisition_required
                and not e.licence_review_required
            ),
            acquired=acquired,
            normalised=record_count > 0,
            indexed=indexed,
            available_for_retrieval=indexed,
            record_count=record_count,
            chunk_count=chunk_count,
            detected_version=(local.get("version") if local else None),
            detected_reference_year=(local.get("year") if local else None),
            local_files=local_files,
            local_file_found=local_file_found,
            needs_manual_acquisition=e.manual_acquisition_required,
            needs_licence_review=e.licence_review_required,
        )
        status.lifecycle = _lifecycle(status, e)
        _apply_origin(status, e, ledger.get(e.source_id), korigins)
        out.append(status)
    return out


def _apply_origin(s: SourceStatus, e: km.SourceEntry, ledger_origins, korigins) -> None:
    """Set data_origin / fixture_only / production_ready.

    Prefers the loader-recorded origin ledger; falls back to the inventory (a
    source with data but no real local file is treated as a synthetic fixture, so
    a fresh checkout without the ledger is still safe).
    """
    if ledger_origins:
        s.data_origin = korigins.resolve_origin(ledger_origins)
        s.fixture_only = korigins.is_fixture_only(ledger_origins)
    elif s.record_count > 0 or s.chunk_count > 0:
        if s.local_file_found:
            s.data_origin = (constants.ORIGIN_AUTHORISED_MANUAL if e.manual_acquisition_required
                             else constants.ORIGIN_OFFICIAL_LOCAL)
            s.fixture_only = False
        else:
            s.data_origin = constants.ORIGIN_SYNTHETIC_FIXTURE
            s.fixture_only = True
    else:
        s.data_origin = None
        s.fixture_only = False

    has_real = s.data_origin in constants.REAL_ORIGINS or s.data_origin == constants.ORIGIN_MIXED
    blocking_licence = e.licence_review_required or e.manual_review_required
    s.production_ready = bool(
        s.available_for_retrieval and has_real and not s.fixture_only and not blocking_licence
    )


def _lifecycle(s: SourceStatus, e: km.SourceEntry) -> str:
    if s.available_for_retrieval:
        return AVAILABLE
    # A local raw file present but not yet normalised/indexed: it is already
    # acquired, so report that rather than "manual acquisition required".
    if s.local_file_found:
        return LOCAL_FILE_FOUND
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
        "local_file_found": sum(1 for s in statuses if s.local_file_found),
        "acquired": sum(1 for s in statuses if s.acquired),
        # Manual acquisition / licence review that is still OUTSTANDING — i.e. the
        # source is neither already available for retrieval nor present locally
        # (a local file or loaded records supersede the manifest flag).
        "manual_acquisition": sum(
            1 for s in statuses
            if s.needs_manual_acquisition and not s.local_file_found
            and not s.available_for_retrieval
        ),
        "licence_review": sum(
            1 for s in statuses
            if s.needs_licence_review and not s.local_file_found
            and not s.available_for_retrieval
        ),
        "structured_records": sum(s.record_count for s in statuses),
        "vector_chunks": sum(s.chunk_count for s in statuses),
        "indexed_narrative": sum(1 for s in statuses if s.chunk_count > 0),
        # Data-origin integrity.
        "production_ready": sum(1 for s in statuses if s.production_ready),
        "fixture_only": sum(1 for s in statuses if s.fixture_only),
        "real_data_sources": sum(
            1 for s in statuses
            if s.data_origin in constants.REAL_ORIGINS or s.data_origin == constants.ORIGIN_MIXED
        ),
    }
