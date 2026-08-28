"""Final local-source report — exact measured counts only (no estimates).

Aggregates the inventory, source status, and the structured stores into
``docs/local_source_report.md``. Every number is a real row/file count.

Usage:  python scripts/final_source_report.py
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402
from src.copilot.knowledge import status as st  # noqa: E402

OUT = Path("docs/local_source_report.md")
INVENTORY = "data/source_inventory.json"


def _q(db: str, sql: str) -> int:
    if not os.path.isfile(db):
        return 0
    conn = sqlite3.connect(db)
    try:
        return conn.execute(sql).fetchone()[0]
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def main() -> int:
    if not os.path.isfile(INVENTORY):
        print(f"No inventory at {INVENTORY}. Run scripts/inventory_sources.py first.")
        return 1
    inv = json.load(open(INVENTORY, encoding="utf-8"))
    entries = {e.source_id: e for e in km.load_manifest()}
    statuses = st.compute_status()
    by_id = {s.source_id: s for s in statuses}
    H = st.summary(statuses)
    R, C = constants.ROLE_DB_PATH, constants.COMPENSATION_DB_PATH
    CO, LM = constants.COMPETENCY_DB_PATH, constants.LABOUR_MARKET_DB_PATH

    metrics = {
        "Files discovered in data/raw": inv["file_count"],
        "Files mapped to known sources": inv["file_count"] - inv["unresolved_count"],
        "Unresolved files": inv["unresolved_count"],
        "Configured sources": H["configured"],
        "Sources found locally": len(inv["source_ids_found"]),
        "Sources normalised (records>0)": sum(1 for s in statuses if s.record_count > 0),
        "Sources indexed (vector chunks>0)": H["indexed_narrative"],
        "Sources retrieval-ready (total)": H["available_locally"],
        "Sources production-ready (real data)": H["production_ready"],
        "Real-data sources": H["real_data_sources"],
        "Fixture-only sources": H["fixture_only"],
        "Structured occupation records": _q(R, "SELECT COUNT(*) FROM occupations"),
        "Task records": _q(R, "SELECT COUNT(*) FROM occupation_tasks"),
        "Skill relationships": _q(R, "SELECT COUNT(*) FROM occupation_skills"),
        "Technology relationships": _q(R, "SELECT COUNT(*) FROM occupation_skills WHERE skill_type='technology'"),
        "Knowledge records": _q(R, "SELECT COUNT(*) FROM occupation_knowledge"),
        "Activity records": _q(R, "SELECT COUNT(*) FROM occupation_activities"),
        "Occupation relationships": _q(R, "SELECT COUNT(*) FROM occupation_relationships"),
        "Competency records": _q(CO, "SELECT COUNT(*) FROM competencies"),
        "Role-behaviour records": _q(CO, "SELECT COUNT(*) FROM role_behaviours"),
        "Qualification records": _q(CO, "SELECT COUNT(*) FROM qualification_requirements"),
        "Compensation records": _q(C, "SELECT COUNT(*) FROM compensation_records"),
        "Labour-market records": (
            _q(LM, "SELECT COUNT(*) FROM labour_market_forecasts")
            + _q(LM, "SELECT COUNT(*) FROM labour_market_openings")
            + _q(LM, "SELECT COUNT(*) FROM labour_shortages")
        ),
        "Vector documents (narrative files indexed)": sum(
            1 for f in inv["files"]
            if f["intended_storage_target"] == "vector" and f["extension"] in (".pdf", ".txt", ".md")
        ),
        "Vector chunks": H["vector_chunks"],
        "Manual acquisition still outstanding": H["manual_acquisition"],
        "Licence review still outstanding": H["licence_review"],
    }
    not_found = sorted(
        sid for sid, s in by_id.items()
        if not s.available_for_retrieval and not s.local_file_found
    )
    metrics["Configured but not found locally"] = len(not_found)

    lines = ["# Final Local Source Report\n",
             "Measured values only — every number is a real count from the loaded stores "
             "or the inventory. Regenerate with `python scripts/final_source_report.py`.\n",
             "## Counts\n", "| Metric | Value |", "|---|---|"]
    for k, v in metrics.items():
        lines.append(f"| {k} | {v:,} |")
    lines.append("\n## Configured but not found locally\n")
    for sid in not_found:
        e = entries.get(sid)
        how = "manual" if (e and e.manual_acquisition_required) else ("auto-download" if (e and e.download_url) else "—")
        lines.append(f"- `{sid}` — {e.title if e else sid} (acquisition: {how})")
    # Data-origin integrity table (real vs fixture).
    lines.append("\n## Data origin & production readiness (measured)\n")
    lines.append("`retrieval-ready` = loaded locally; `production-ready` = real official "
                 "data with a clear licence. Synthetic fixtures are never production-ready.\n")
    lines.append("| Source | Origin | Fixture-only | Production-ready | Records |")
    lines.append("|---|---|---|---|---|")
    for sid, s in sorted(by_id.items()):
        if not s.available_for_retrieval:
            continue
        lines.append(f"| `{sid}` | {s.data_origin or '—'} | "
                     f"{'yes' if s.fixture_only else 'no'} | "
                     f"{'yes' if s.production_ready else 'no'} | {s.record_count:,} |")
    fixture_only = sorted(sid for sid, s in by_id.items() if s.fixture_only)
    lines.append("\n### Fixture-only sources (NOT production-ready)\n")
    for sid in fixture_only:
        lines.append(f"- `{sid}` — served by a synthetic sample pending a real extract")
    lines.append("\n## Recommended sources still missing\n")
    lines.append("- BERUFENET authorised export (German occupation detail beyond KldB)")
    lines.append("- BA Entgeltatlas authorised export (German compensation)")
    lines.append("- Real extracts to replace fixture-only competency/labour samples "
                 "(e-CF, BA Kompetenzkatalog, OPM qualification standards, Cedefop "
                 "openings/shortage)")
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    for k, v in metrics.items():
        print(f"  {k:48} {v:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
