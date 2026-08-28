"""Measured knowledge-coverage report for the loaded structured stores.

Reports, from ACTUAL loaded data (never estimates), which sources support each
coverage area, plus the four acquisition lists (available/current,
available/outdated, configured-not-found, recommended-missing) and a version
note per source. Writes ``docs/knowledge_coverage_report.md``.

Offline and read-only. Run the loaders first (``scripts/load_local_sources.py``,
``scripts/load_competencies.py``, ``scripts/load_labour_market.py``).

Usage:  python scripts/knowledge_coverage.py
"""

from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402
from src.copilot.knowledge import status as kstatus  # noqa: E402

OUT = Path("docs/knowledge_coverage_report.md")

# Coverage area -> (db_path, sql to count per source_id). Only measured rows count.
_AREAS = [
    ("Occupations", constants.ROLE_DB_PATH, "SELECT source_id, COUNT(*) FROM occupations GROUP BY source_id"),
    ("Responsibilities / tasks", constants.ROLE_DB_PATH, "SELECT source_id, COUNT(*) FROM occupation_tasks GROUP BY source_id"),
    ("Skills", constants.ROLE_DB_PATH, "SELECT source_id, COUNT(*) FROM occupation_skills GROUP BY source_id"),
    ("Knowledge", constants.ROLE_DB_PATH, "SELECT source_id, COUNT(*) FROM occupation_knowledge GROUP BY source_id"),
    ("Work activities / context", constants.ROLE_DB_PATH, "SELECT source_id, COUNT(*) FROM occupation_activities GROUP BY source_id"),
    ("Technologies", constants.ROLE_DB_PATH, "SELECT source_id, COUNT(*) FROM occupation_skills WHERE skill_type='technology' GROUP BY source_id"),
    ("Career transitions (relationships)", constants.ROLE_DB_PATH, "SELECT source_id, COUNT(*) FROM occupation_relationships GROUP BY source_id"),
    ("Competencies", constants.COMPETENCY_DB_PATH, "SELECT source_id, COUNT(*) FROM competencies GROUP BY source_id"),
    ("Seniority / interview behaviours", constants.COMPETENCY_DB_PATH, "SELECT source_id, COUNT(*) FROM role_behaviours GROUP BY source_id"),
    ("Qualification requirements", constants.COMPETENCY_DB_PATH, "SELECT source_id, COUNT(*) FROM qualification_requirements GROUP BY source_id"),
    ("Compensation", constants.COMPENSATION_DB_PATH, "SELECT source_id, COUNT(*) FROM compensation_records GROUP BY source_id"),
    ("Future demand (forecast)", constants.LABOUR_MARKET_DB_PATH, "SELECT source_id, COUNT(*) FROM labour_market_forecasts GROUP BY source_id"),
    ("Future job openings", constants.LABOUR_MARKET_DB_PATH, "SELECT source_id, COUNT(*) FROM labour_market_openings GROUP BY source_id"),
    ("Shortages", constants.LABOUR_MARKET_DB_PATH, "SELECT source_id, COUNT(*) FROM labour_shortages GROUP BY source_id"),
]

# Best-known latest official versions (offline; NOT fetched live). Used only to
# classify local copies; where unknown we say VERSION_UNKNOWN and never auto-update.
_LATEST_KNOWN = {
    "onet": "31.0",
    "isco08": "ISCO-08",
    "esco": "v1.2.1",
    "esco_matrix": "v1.2.1",
}


def _counts(db: str, sql: str) -> dict[str, int]:
    if not os.path.isfile(db):
        return {}
    conn = sqlite3.connect(db)
    try:
        return {r[0]: r[1] for r in conn.execute(sql) if r[0]}
    except sqlite3.OperationalError:
        return {}
    finally:
        conn.close()


def _version_class(local: str | None, latest: str | None) -> str:
    if not local:
        return "VERSION_UNKNOWN"
    if not latest:
        return "VERSION_UNKNOWN"
    return "CURRENT" if str(local).strip() == str(latest).strip() else "OLDER_BUT_USABLE"


def main() -> int:
    entries = {e.source_id: e for e in km.load_manifest(constants.SOURCE_MANIFEST_PATH)}
    statuses = {s.source_id: s for s in kstatus.compute_status(constants.SOURCE_MANIFEST_PATH)}

    lines = ["# Knowledge Coverage Report\n"]
    lines.append("Measured from the loaded structured stores — every number is a real "
                 "row count, never an estimate. Only sources with data actually loaded "
                 "are listed as active coverage.\n")

    lines.append("## Coverage by area (measured)\n")
    for area, db, sql in _AREAS:
        counts = _counts(db, sql)
        lines.append(f"### {area}")
        if not counts:
            lines.append("- _no source loaded for this area yet_\n")
            continue
        for sid, n in sorted(counts.items(), key=lambda kv: -kv[1]):
            title = entries[sid].title if sid in entries else sid
            lines.append(f"- {title} (`{sid}`) — {n:,} records")
        lines.append("")

    # Four acquisition lists.
    available, outdated, not_found, recommended = [], [], [], []
    for sid, s in statuses.items():
        e = entries.get(sid)
        latest = _LATEST_KNOWN.get(sid)
        vclass = _version_class(s.detected_version, latest)
        if s.available_for_retrieval:
            (outdated if vclass == "OUTDATED" else available).append((sid, s, vclass))
        elif s.local_file_found:
            available.append((sid, s, vclass))  # present locally, ready to load/index
        else:
            not_found.append((sid, s, vclass))

    lines.append("## Acquisition lists\n")
    lines.append("### 1. Available locally and current")
    for sid, s, v in sorted(available):
        lines.append(f"- `{sid}` — lifecycle {s.lifecycle}, {s.record_count:,} records, version {s.detected_version or '—'} ({v})")
    lines.append("")
    lines.append("### 2. Available locally but outdated")
    lines.append("- _none detected_" if not outdated else "")
    for sid, s, v in sorted(outdated):
        lines.append(f"- `{sid}` — local {s.detected_version}, newer official version exists")
    lines.append("")
    lines.append("### 3. Configured but NOT found locally")
    for sid, s, v in sorted(not_found):
        e = entries.get(sid)
        how = "manual" if (e and e.manual_acquisition_required) else ("auto-download" if (e and e.download_url) else "—")
        lines.append(f"- `{sid}` — {e.title if e else sid} (acquisition: {how})")
    lines.append("")
    lines.append("### 4. Recommended sources not yet available")
    lines.append("- BLS Occupational Outlook Handbook structured export (adds US outlook narrative + entry education)")
    lines.append("- BERUFENET authorised export (adds German occupation detail beyond KldB)")
    lines.append("- BA Entgeltatlas authorised export (adds German compensation, currently sample-only)")
    lines.append("")

    lines.append("## Version notes (offline)\n")
    lines.append("Local versions are reported as detected; latest official versions were "
                 "**not fetched live** (local-first, no network). Nothing is auto-updated.\n")
    lines.append("| Source | Local version | Known latest | Class |")
    lines.append("|---|---|---|---|")
    for sid, s in sorted(statuses.items()):
        if not s.local_file_found and not s.available_for_retrieval:
            continue
        latest = _LATEST_KNOWN.get(sid, "—")
        lines.append(f"| `{sid}` | {s.detected_version or '—'} | {latest} | {_version_class(s.detected_version, _LATEST_KNOWN.get(sid))} |")
    lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    print(f"Available/current: {len(available)} | not found: {len(not_found)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
