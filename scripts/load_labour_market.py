"""Load labour-market files into the labour-market repository (SQLite).

Reads source-shaped JSON files (Cedefop Skills Forecast, future job openings,
shortage index) from a directory and loads them into
``data/knowledge/labour_market.db``. Dispatch is by filename. The DB is rebuilt
each run (derived store) so the load is idempotent.

By default it reads the committed offline samples so the pipeline is runnable
without downloads; point --source at real normalised extracts for production.

Usage:
  python scripts/load_labour_market.py
  python scripts/load_labour_market.py --source data/knowledge/raw --db data/knowledge/labour_market.db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import normalisers_ext as norm  # noqa: E402
from src.copilot.knowledge.structured_ext import LabourMarketRepository  # noqa: E402

_DEFAULT_SOURCE = "evaluations/knowledge_samples"


def _dispatch(path: str, repo: LabourMarketRepository) -> int:
    name = os.path.basename(path).lower()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    added = 0
    if name.startswith("cedefop_forecast"):
        for f in norm.normalise_cedefop_forecast(data):
            repo.add_forecast(f); added += 1
    elif name.startswith("cedefop_openings"):
        for o in norm.normalise_cedefop_openings(data):
            repo.add_openings(o); added += 1
    elif name.startswith("cedefop_shortage"):
        for s in norm.normalise_cedefop_shortage(data):
            repo.add_shortage(s); added += 1
    return added


_PREFIXES = ("cedefop_forecast", "cedefop_openings", "cedefop_shortage")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load labour-market data into the labour-market DB.")
    parser.add_argument("--source", default=_DEFAULT_SOURCE)
    parser.add_argument("--db", default=constants.LABOUR_MARKET_DB_PATH)
    args = parser.parse_args(argv)

    if not os.path.isdir(args.source):
        print(f"No source directory at {args.source}. See data/source_manifest.json.")
        return 0
    files = [p for p in sorted(Path(args.source).glob("*.json"))
             if p.name.lower().startswith(_PREFIXES)]

    # Real BLS Employment Projections (US), if present locally.
    from src.copilot.knowledge import local_readers as lr

    bls_fc, bls_open = lr.read_bls_projections()

    if not files and not (bls_fc or bls_open):
        print(f"No labour-market source files found under {args.source}.")
        return 0

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    if os.path.isfile(args.db):
        os.remove(args.db)
    repo = LabourMarketRepository(args.db)
    total = 0
    for path in files:
        try:
            added = _dispatch(str(path), repo)
            total += added
            print(f"  ✓ {path.name}: {added} record(s)")
        except Exception as exc:  # noqa: BLE001 - fail safely, keep going
            print(f"  ✗ {path.name}: {type(exc).__name__}")
    if bls_fc or bls_open:
        for f in bls_fc:
            repo.add_forecast(f)
        for o in bls_open:
            repo.add_openings(o)
        total += len(bls_fc) + len(bls_open)
        print(f"  ✓ BLS Employment Projections (local): "
              f"{len(bls_fc)} forecast(s), {len(bls_open)} openings")
    counts = repo.counts()
    repo.close()
    print(f"\nLabour-market DB {args.db}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
