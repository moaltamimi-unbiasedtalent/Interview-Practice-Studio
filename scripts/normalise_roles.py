"""Normalise role source files into the structured role repository (SQLite).

Reads source-shaped JSON files (ESCO / O*NET / ISCO / KldB) from a directory and
loads them into ``data/knowledge/roles.db``. Dispatch is by filename prefix
(roles_onet*, roles_esco*, isco*, kldb*). Idempotent: re-ingesting the same
occupation code replaces its rows rather than duplicating.

By default it reads the committed synthetic samples so the pipeline is runnable
without downloads; point --source at real normalised extracts for production.

Usage:
  python scripts/normalise_roles.py
  python scripts/normalise_roles.py --source data/knowledge/raw --db data/knowledge/roles.db
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import normalisers as norm  # noqa: E402
from src.copilot.knowledge.roles import RoleRepository  # noqa: E402

_DEFAULT_SOURCE = "evaluations/knowledge_samples"


def _dispatch(path: str, repo: RoleRepository) -> int:
    name = os.path.basename(path).lower()
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    added = 0
    if name.startswith("roles_onet"):
        for row in data:
            repo.add_occupation(norm.normalise_onet(row)); added += 1
    elif name.startswith("roles_esco"):
        for row in data:
            repo.add_occupation(norm.normalise_esco(row)); added += 1
    elif name.startswith("isco"):
        for occ in norm.normalise_isco(data):
            repo.add_occupation(occ); added += 1
    elif name.startswith("kldb"):
        for row in data:
            repo.add_occupation(norm.normalise_kldb(row)); added += 1
    return added


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Normalise role sources into the role DB.")
    parser.add_argument("--source", default=_DEFAULT_SOURCE)
    parser.add_argument("--db", default=constants.ROLE_DB_PATH)
    args = parser.parse_args(argv)

    if not os.path.isdir(args.source):
        print(f"No source directory at {args.source}. See data/source_manifest.json.")
        return 0
    files = [p for p in sorted(Path(args.source).glob("*.json"))]
    role_files = [p for p in files if p.name.lower().startswith(("roles_", "isco", "kldb"))]
    if not role_files:
        print(f"No role source files found under {args.source}.")
        return 0

    os.makedirs(os.path.dirname(args.db) or ".", exist_ok=True)
    repo = RoleRepository(args.db)
    total = 0
    for path in role_files:
        try:
            added = _dispatch(str(path), repo)
            total += added
            print(f"  ✓ {path.name}: {added} occupation(s)")
        except Exception as exc:  # noqa: BLE001 - fail safely, keep going
            print(f"  ✗ {path.name}: {type(exc).__name__}")
    counts = repo.counts()
    repo.close()
    print(f"\nRole DB {args.db}: {counts['occupations']} occupations, "
          f"{counts['occupation_skills']} skills, {counts['occupation_tasks']} tasks.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
