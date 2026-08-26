"""Show knowledge-source health and (re)generate ``data/source_status.json``.

Offline and read-only against the network. Derives the mutable runtime lifecycle
of every configured source from what is actually on disk (structured stores,
vector manifest, downloads) — a source in the manifest is NEVER assumed loaded.
The static catalogue lives in ``data/source_manifest.json``; the generated,
measured status lives in ``data/source_status.json``.

Usage:
  python scripts/source_status.py            # print table + write source_status.json
  python scripts/source_status.py --no-write  # print only
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402
from src.copilot.knowledge import status as st  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Knowledge-source health + status generation.")
    parser.add_argument("--no-write", action="store_true", help="print only, do not write source_status.json")
    parser.add_argument("--manifest", default=constants.SOURCE_MANIFEST_PATH)
    parser.add_argument("--out", default=constants.SOURCE_STATUS_PATH)
    args = parser.parse_args(argv)

    try:
        entries = {e.source_id: e for e in km.load_manifest(args.manifest)}
    except FileNotFoundError:
        print(f"No manifest at {args.manifest}.")
        return 1

    statuses = st.compute_status(args.manifest)
    health = st.summary(statuses)

    print("Knowledge health")
    print("----------------")
    print(f"  configured sources        : {health['configured']}")
    print(f"  available for retrieval    : {health['available_locally']}")
    print(f"  acquired (on disk)         : {health['acquired']}")
    print(f"  manual acquisition needed  : {health['manual_acquisition']}")
    print(f"  licence review needed      : {health['licence_review']}")
    print(f"  structured records loaded  : {health['structured_records']}")
    print()

    header = f"{'source_id':<32}{'group':<16}{'records':>8}  {'lifecycle'}"
    print(header)
    print("-" * (len(header) + 6))
    for s in statuses:
        group = entries[s.source_id].group if s.source_id in entries else ""
        print(f"{s.source_id:<32}{group:<16}{s.record_count:>8}  {s.lifecycle}")

    if not args.no_write:
        st.write_status(args.out, args.manifest)
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
