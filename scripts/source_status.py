"""Show knowledge-source health: configured sources, counts, licence/manual flags.

Offline and read-only. Does not expose filesystem secrets.

Usage:  python scripts/source_status.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402


def _role_count() -> int:
    if not os.path.isfile(constants.ROLE_DB_PATH):
        return 0
    from src.copilot.knowledge.roles import RoleRepository

    repo = RoleRepository(constants.ROLE_DB_PATH)
    n = repo.counts().get("occupations", 0)
    repo.close()
    return n


def _comp_count() -> int:
    if not os.path.isfile(constants.COMPENSATION_DB_PATH):
        return 0
    from src.copilot.knowledge.compensation import CompensationRepository

    repo = CompensationRepository(constants.COMPENSATION_DB_PATH)
    n = repo.count()
    repo.close()
    return n


def main() -> int:
    try:
        entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
    except FileNotFoundError:
        print(f"No manifest at {constants.SOURCE_MANIFEST_PATH}.")
        return 1

    print(f"Configured sources: {len(entries)}")
    print(f"Structured occupations indexed : {_role_count()}")
    print(f"Compensation records indexed   : {_comp_count()}")
    print()
    header = f"{'source_id':<22}{'type':<22}{'auth':<5}{'status':<8}{'licence'}"
    print(header)
    print("-" * len(header))
    for e in entries:
        status = "manual" if e.manual_acquisition_required else "auto"
        licence = "review" if e.licence_review_required else (e.licence or "—")
        print(f"{e.source_id:<22}{e.source_type:<22}{e.authority_level:<5}{status:<8}{licence}")
    manual = km.manual_sources(entries)
    if manual:
        print(f"\nManual acquisition required for: {', '.join(e.source_id for e in manual)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
