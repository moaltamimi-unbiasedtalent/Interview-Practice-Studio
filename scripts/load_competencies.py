"""Load competency/behaviour framework files into the competency repository.

Reads source-shaped JSON files (DigComp, NICE, e-CF, BA Kompetenzkatalog, UK
Civil Service Success Profiles, OPM Qualification Standards) from a directory and
loads them into ``data/knowledge/competencies.db``. Dispatch is by filename.
The DB is rebuilt each run (derived store) so the load is idempotent.

By default it reads the committed offline samples so the pipeline is runnable
without downloads; point --source at real normalised extracts for production.

Usage:
  python scripts/load_competencies.py
  python scripts/load_competencies.py --source data/knowledge/raw --db data/knowledge/competencies.db
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
from src.copilot.knowledge.structured_ext import CompetencyRepository  # noqa: E402

_DEFAULT_SOURCE = "evaluations/knowledge_samples"


def _dispatch(path: str, repo: CompetencyRepository) -> int:
    name = os.path.basename(path).lower()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    added = 0
    if name.startswith("digcomp"):
        comps, levels = norm.normalise_digcomp(data)
        for c in comps:
            repo.add_competency(c); added += 1
        for lv in levels:
            repo.add_level(lv); added += 1
    elif name.startswith("nice"):
        comps, links = norm.normalise_nice(data)
        for c in comps:
            repo.add_competency(c); added += 1
        for oc in links:
            repo.add_occupation_competency(oc); added += 1
    elif name.startswith("ecf"):
        for c in norm.normalise_ecf(data):
            repo.add_competency(c); added += 1
    elif name.startswith("ba_kompetenzkatalog"):
        for c in norm.normalise_ba_kompetenzkatalog(data):
            repo.add_competency(c); added += 1
    elif name.startswith("civil_service_success_profiles"):
        for b in norm.normalise_civil_service_success_profiles(data):
            repo.add_behaviour(b); added += 1
    elif name.startswith("opm_qualification_standards"):
        for q in norm.normalise_opm_qualification_standards(data):
            repo.add_qualification(q); added += 1
    return added


_PREFIXES = ("digcomp", "nice", "ecf", "ba_kompetenzkatalog",
             "civil_service_success_profiles", "opm_qualification_standards")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load competency frameworks into the competency DB.")
    parser.add_argument("--source", default=_DEFAULT_SOURCE)
    parser.add_argument("--db", default=constants.COMPETENCY_DB_PATH)
    args = parser.parse_args(argv)

    if not os.path.isdir(args.source):
        print(f"No source directory at {args.source}. See data/source_manifest.json.")
        return 0
    files = [p for p in sorted(Path(args.source).glob("*.json"))
             if p.name.lower().startswith(_PREFIXES)]
    if not files:
        print(f"No competency source files found under {args.source}.")
        return 0

    # Prefer the real structured NICE workbook over the tiny NICE sample.
    from src.copilot.knowledge import local_readers as lr

    nice_real = lr.read_nice_structured()
    if nice_real:
        files = [p for p in files if not p.name.lower().startswith("nice")]

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    if os.path.isfile(args.db):
        os.remove(args.db)
    repo = CompetencyRepository(args.db)
    total = 0
    for path in files:
        try:
            added = _dispatch(str(path), repo)
            total += added
            print(f"  ✓ {path.name}: {added} record(s)")
        except Exception as exc:  # noqa: BLE001 - fail safely, keep going
            print(f"  ✗ {path.name}: {type(exc).__name__}")
    if nice_real:
        for c in nice_real:
            repo.add_competency(c)
        total += len(nice_real)
        print(f"  ✓ NICE Framework Components (local): {len(nice_real)} record(s)")
    counts = repo.counts()
    repo.close()
    print(f"\nCompetency DB {args.db}: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
