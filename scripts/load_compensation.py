"""Load a compensation CSV into the structured compensation repository (SQLite).

Reads a CSV matching the compensation schema and loads it into
``data/knowledge/compensation.db``. The DB is rebuilt each run (it is a derived
store, not curated content) so the load is idempotent. Context (currency, period,
statistic, geography, year) is preserved exactly — figures are never normalised
or merged across countries.

By default it loads the committed synthetic sample.

Usage:
  python scripts/load_compensation.py
  python scripts/load_compensation.py --csv path/to/compensation.csv --db data/knowledge/compensation.db
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge.compensation import CompensationRecord, CompensationRepository  # noqa: E402

_DEFAULT_CSV = "evaluations/knowledge_samples/compensation.csv"
_INTS = {"year"}
_FLOATS = {"value", "lower_bound", "upper_bound"}


def _coerce(row: dict) -> dict:
    out = {}
    for k, v in row.items():
        if v == "" or v is None:
            out[k] = None
        elif k in _INTS:
            out[k] = int(float(v))
        elif k in _FLOATS:
            out[k] = float(v)
        else:
            out[k] = v
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load compensation CSV into the compensation DB.")
    parser.add_argument("--csv", default=_DEFAULT_CSV)
    parser.add_argument("--db", default=constants.COMPENSATION_DB_PATH)
    args = parser.parse_args(argv)

    if not os.path.isfile(args.csv):
        print(f"No CSV at {args.csv}. See data/source_manifest.json for sources.")
        return 0

    # Rebuild the derived store for an idempotent load.
    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    if os.path.isfile(args.db):
        os.remove(args.db)
    repo = CompensationRepository(args.db)

    loaded = 0
    with open(args.csv, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                repo.add(CompensationRecord(**_coerce(row)))
                loaded += 1
            except Exception as exc:  # noqa: BLE001 - skip bad rows, keep going
                print(f"  ✗ skipped a row: {type(exc).__name__}")
    countries = repo.countries()
    repo.close()
    print(f"Compensation DB {args.db}: {loaded} records across {countries}.")
    print("Figures preserve currency/period/statistic/year — never compared across contexts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
