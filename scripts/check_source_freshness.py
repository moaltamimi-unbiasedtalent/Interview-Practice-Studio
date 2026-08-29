"""Report knowledge-source freshness (OPT-8) — advisory, offline, no downloads.

Computes each available source's freshness (CURRENT / REFRESH DUE / UNKNOWN) from
its detected reference year and manifest refresh cadence, and prints a table plus
a summary. It never contacts the network and never modifies any data.

By default it always exits 0 (advisory). Pass --strict to exit non-zero when any
available source is REFRESH DUE — useful for a scheduled reminder, but it is NOT
part of the build gate (a stale public dataset must never fail CI).

Usage:
    python scripts/check_source_freshness.py
    python scripts/check_source_freshness.py --strict
    python scripts/check_source_freshness.py --year 2026   # pin the "now" year
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.knowledge import status as S  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report knowledge-source freshness.")
    parser.add_argument("--strict", action="store_true",
                        help="exit non-zero if any available source is REFRESH DUE")
    parser.add_argument("--year", type=int, default=None,
                        help="pin the current year (default: today, UTC)")
    args = parser.parse_args(argv)

    statuses = S.compute_status(current_year=args.year)
    available = [s for s in statuses if s.available_for_retrieval]
    summ = S.summary(statuses)

    print("Knowledge-source freshness")
    print("=" * 60)
    print(f"{'source':30} {'year':>5}  freshness")
    print("-" * 60)
    for s in sorted(available, key=lambda x: (x.freshness, x.source_id)):
        yr = s.detected_reference_year or "?"
        print(f"{s.source_id:30} {str(yr):>5}  {s.freshness}")

    print("-" * 60)
    print(f"CURRENT: {summ['fresh_current']} · REFRESH DUE: {summ['refresh_due']} · "
          f"UNKNOWN: {summ['freshness_unknown']} (of {len(available)} available)")
    print("UNKNOWN = no reference year or no defined refresh cadence; not a defect.")

    due = [s.source_id for s in available if s.freshness == S.FRESHNESS_DUE]
    if due:
        print("\nREFRESH DUE:")
        for sid in due:
            print(f"  - {sid}")
        print("Re-acquire the latest release from the source, then re-run the "
              "relevant loader (see scripts/refresh_public_sources.py --dry-run).")

    if args.strict and due:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
