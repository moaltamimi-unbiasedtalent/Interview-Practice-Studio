"""Plan a refresh of public knowledge sources (OPT-8) — DRY-RUN ONLY.

This helper NEVER downloads anything. It reports, for each source flagged
REFRESH DUE (or all sources with --all), where to obtain the latest release and
which loader to run once the file is placed under data/raw/. Actual acquisition
is deliberately manual: it respects the local-source-priority rule (do not
re-download or overwrite raw files without explicit human action) and the licence
posture of each source.

Usage:
    python scripts/refresh_public_sources.py --dry-run           # due sources only
    python scripts/refresh_public_sources.py --dry-run --all     # every source
    python scripts/refresh_public_sources.py --dry-run --year 2026
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.knowledge import manifest as km  # noqa: E402
from src.copilot.knowledge import status as S  # noqa: E402

# Loader hint per storage target (what to run after placing the file in data/raw).
_LOADER_HINT = {
    "structured_role": "scripts/load_local_sources.py / scripts/normalise_roles.py",
    "compensation": "scripts/load_compensation.py",
    "labour_market": "scripts/load_labour_market.py",
    "competency": "scripts/load_competencies.py",
    "credential": "scripts/load_credentials.py",
    "vector": "scripts/ingest_local_narrative.py",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan (dry-run) a public-source refresh.")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="report only (the default and only supported mode)")
    parser.add_argument("--all", action="store_true",
                        help="include all sources, not just REFRESH DUE")
    parser.add_argument("--year", type=int, default=None, help="pin the current year")
    parser.add_argument("--execute", action="store_true",
                        help="not supported — acquisition is manual by design")
    args = parser.parse_args(argv)

    if args.execute:
        print("Refusing to auto-download. Acquisition is manual by design: obtain "
              "the file from the source URL, place it under data/raw/, then run the "
              "loader. This preserves local-source priority and licence review.")
        return 2

    entries = {e.source_id: e for e in km.load_manifest()}
    statuses = S.compute_status(current_year=args.year)
    targets = [s for s in statuses
               if args.all or s.freshness == S.FRESHNESS_DUE]

    print("Public-source refresh plan (DRY-RUN — nothing is downloaded)")
    print("=" * 66)
    if not targets:
        print("No sources are REFRESH DUE. Use --all to list every source.")
        return 0

    for s in sorted(targets, key=lambda x: x.source_id):
        e = entries.get(s.source_id)
        if e is None:
            continue
        if e.manual_acquisition_required or e.licence_review_required:
            note = "MANUAL / LICENCE-RESTRICTED — acquire per licence terms"
        else:
            note = "public — re-download the latest release"
        loader = _LOADER_HINT.get(e.storage_target or "", "see docs/rebuild_knowledge_base.md")
        print(f"\n[{s.source_id}] {e.title}")
        print(f"  freshness : {s.freshness} (year {s.detected_reference_year or '?'})")
        print(f"  acquire   : {note}")
        print(f"  source    : {e.source_url or '—'}")
        print(f"  download  : {e.download_url or '—'}")
        print(f"  then run  : {loader}")

    print("\nAfter placing new files under data/raw/, re-run the loader(s) above, "
          "then scripts/source_status.py to refresh status.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
