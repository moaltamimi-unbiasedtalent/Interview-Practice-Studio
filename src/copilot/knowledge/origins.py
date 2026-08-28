"""Per-source data-origin ledger.

Records where each source's loaded data actually came from — real official files
vs synthetic test fixtures — so the app never presents a hand-authored sample as
loaded official data. Loaders call :func:`record_origins` as they load; status
derivation reads the ledger (falling back to inventory when it is absent, e.g. a
fresh checkout).

The ledger is a small JSON map ``{source_id: [origin, ...]}`` under
``data/knowledge/`` (git-ignored, derived). A source may legitimately carry more
than one origin (e.g. a real narrative PDF plus a fixture structured sample).
"""

from __future__ import annotations

import json
import os

from src.copilot import constants

__all__ = [
    "record_origins", "load_origins", "clear_origins",
    "resolve_origin", "is_fixture_only",
]

# Trust order for choosing a single representative origin (most-trusted first).
_TRUST = [
    constants.ORIGIN_OFFICIAL_LOCAL,
    constants.ORIGIN_OFFICIAL_DOWNLOAD,
    constants.ORIGIN_AUTHORISED_MANUAL,
    constants.ORIGIN_API_SNAPSHOT,
    constants.ORIGIN_SYNTHETIC_FIXTURE,
]


def load_origins(path: str = constants.DATA_ORIGINS_PATH) -> dict[str, list[str]]:
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    origins = data.get("origins", {})
    # Normalise to lists.
    return {k: (v if isinstance(v, list) else [v]) for k, v in origins.items()}


def record_origins(mapping: dict[str, str], path: str = constants.DATA_ORIGINS_PATH) -> None:
    """Merge ``{source_id: origin}`` into the ledger (adds, never clobbers)."""
    current = load_origins(path)
    for sid, origin in mapping.items():
        if origin not in constants.DATA_ORIGINS:
            continue
        existing = current.setdefault(sid, [])
        if origin not in existing:
            existing.append(origin)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"origins": current}, handle, indent=2)


def clear_origins(path: str = constants.DATA_ORIGINS_PATH) -> None:
    if os.path.isfile(path):
        os.remove(path)


def resolve_origin(origins: list[str] | None) -> str | None:
    """Collapse a source's recorded origins into one representative label.

    Multiple *real* origins collapse to ``mixed``; a single origin returns itself;
    an empty list returns None (origin unknown).
    """
    if not origins:
        return None
    real = [o for o in origins if o in constants.REAL_ORIGINS]
    if len(set(real)) > 1:
        return constants.ORIGIN_MIXED
    if real:
        return real[0]
    return constants.ORIGIN_SYNTHETIC_FIXTURE


def is_fixture_only(origins: list[str] | None) -> bool:
    """True when a source has data but every recorded origin is a fixture."""
    if not origins:
        return False
    return all(o == constants.ORIGIN_SYNTHETIC_FIXTURE for o in origins)
