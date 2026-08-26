"""Best-effort download of *auto-downloadable* sources from the manifest.

Only fetches sources that have a direct download URL and are not flagged
manual/licence-review. Never scrapes; skips manual sources and reports them.
Idempotent (skips files already present) and fails safely per source.

Usage:  python scripts/download_sources.py [--dest data/knowledge/downloads]
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Download auto-available knowledge sources.")
    parser.add_argument("--dest", default="data/knowledge/downloads")
    args = parser.parse_args(argv)
    os.makedirs(args.dest, exist_ok=True)

    entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
    auto = km.auto_downloadable(entries)
    manual = km.manual_sources(entries)

    print(f"Auto-downloadable: {len(auto)} · manual: {len(manual)}")
    ok = failed = skipped = 0
    for e in auto:
        target = os.path.join(args.dest, f"{e.source_id}.bin")
        if os.path.isfile(target):
            print(f"  = {e.source_id}: already present (skip)")
            skipped += 1
            continue
        try:
            import httpx

            resp = httpx.get(e.download_url, timeout=30, follow_redirects=True)
            resp.raise_for_status()
            with open(target, "wb") as handle:
                handle.write(resp.content)
            print(f"  ✓ {e.source_id}: {len(resp.content)} bytes")
            ok += 1
        except Exception as exc:  # noqa: BLE001 - fail safely, keep going
            print(f"  ✗ {e.source_id}: download failed ({type(exc).__name__})")
            failed += 1

    if manual:
        print("\nManual acquisition required (not downloaded):")
        for e in manual:
            print(f"  - {e.source_id}: {e.source_url or '(see publisher)'}")
    print(f"\nDone. ok={ok} skipped={skipped} failed={failed}")
    print("Note: downloaded datasets are git-ignored; do not commit licensed/large files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
