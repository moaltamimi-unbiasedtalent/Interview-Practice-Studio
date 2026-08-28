"""Build the structured stores from the REAL local files under ``data/raw``.

Local-first: this rebuilds ``roles.db`` (O*NET, ESCO, ISCO-08, KldB) and
``compensation.db`` (BLS OEWS, ONS ASHE) from the user's actual datasets — no
network, no fabrication. Derived stores are rebuilt each run, so the load is
idempotent. Sources not present locally as structured data (competency/labour
frameworks that ship only as PDFs) are left to their sample loaders / the vector
lane; this script never invents records for them.

Usage:
  python scripts/load_local_sources.py                 # roles + compensation
  python scripts/load_local_sources.py --only roles
  python scripts/load_local_sources.py --only compensation
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import local_readers as lr  # noqa: E402
from src.copilot.knowledge.compensation import CompensationRepository  # noqa: E402
from src.copilot.knowledge.roles import RoleRepository  # noqa: E402


def _fast(conn) -> None:
    # Derived store rebuilt each run — safe to relax durability for a fast load.
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA journal_mode=MEMORY")


def _fresh(path: str) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.isfile(path):
        os.remove(path)


def _namespace(occ):
    """Prefix the occupation code (and its relationship targets) with the source.

    Different taxonomies reuse the same numeric codes (ISCO "1" vs KldB "1"), so
    the single-column primary key needs a globally unique, provenance-tagged code.
    ``source_id`` still records the origin, and relationship links stay resolvable
    within the source.
    """
    sid = occ.source_id
    occ.occupation_code = f"{sid}:{occ.occupation_code}"
    for r in occ.relationships:
        r.related_code = f"{sid}:{r.related_code}"
    return occ


def load_roles(db: str = constants.ROLE_DB_PATH) -> dict:
    _fresh(db)
    repo = RoleRepository(db)
    _fast(repo._conn)
    counts: dict[str, int] = {}
    for name, reader in [
        ("onet", lr.read_onet),
        ("esco", lr.read_esco),
        ("isco08", lr.read_isco),
        ("kldb", lr.read_kldb),
        ("bls_ooh", lr.read_ooh),
        ("bls_projections", lr.read_bls_ep_characteristics),
    ]:
        t = time.time()
        occs = reader()
        for occ in occs:
            repo.add_occupation(_namespace(occ))
        counts[name] = len(occs)
        print(f"  ✓ {name}: {len(occs)} occupation(s) in {time.time() - t:.1f}s")
    totals = repo.counts()
    repo.close()
    from src.copilot.knowledge import origins as korigins
    korigins.record_origins({name: constants.ORIGIN_OFFICIAL_LOCAL
                             for name, n in counts.items() if n})
    print(f"Role DB {db}: {totals['occupations']} occupations, "
          f"{totals['occupation_skills']} skills, {totals['occupation_tasks']} tasks.")
    return {"by_source": counts, "totals": totals}


def load_compensation(db: str = constants.COMPENSATION_DB_PATH) -> dict:
    _fresh(db)
    repo = CompensationRepository(db)
    _fast(repo._conn)
    counts: dict[str, int] = {}
    for name, reader in [("bls_oews", lr.read_oews), ("ons_ashe", lr.read_ashe)]:
        t = time.time()
        recs = reader()
        for r in recs:
            repo.add(r)
        counts[name] = len(recs)
        print(f"  ✓ {name}: {len(recs)} record(s) in {time.time() - t:.1f}s")
    total = repo.count()
    repo.close()
    from src.copilot.knowledge import origins as korigins
    korigins.record_origins({name: constants.ORIGIN_OFFICIAL_LOCAL
                             for name, n in counts.items() if n})
    print(f"Compensation DB {db}: {total} records across {counts}.")
    return {"by_source": counts, "total": total}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build structured stores from local data/raw.")
    parser.add_argument("--only", choices=["roles", "compensation"], default=None)
    args = parser.parse_args(argv)

    if args.only in (None, "roles"):
        print("Roles (O*NET, ESCO, ISCO-08, KldB):")
        load_roles()
    if args.only in (None, "compensation"):
        print("Compensation (BLS OEWS, ONS ASHE):")
        load_compensation()
    return 0


if __name__ == "__main__":
    sys.exit(main())
