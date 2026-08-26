"""KB-2 knowledge-expansion evaluation (offline, deterministic).

Measures the expanded knowledge system without touching the preserved 11R / 11R-A
baseline artifacts. It writes ONLY under ``evaluations/knowledge_expansion/``:

  routing_results.csv     — per-case lane routing accuracy (new + existing lanes)
  geo_results.csv         — per-case geographic source precedence
  coverage.csv            — per-source measured lifecycle + record counts
  results.md              — human-readable summary (coverage, routing, provenance)

No network calls, no paid LLM calls; everything runs against committed samples
and the local structured stores. Run the load scripts first for full coverage.

Usage:  python scripts/eval_knowledge_expansion.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402
from src.copilot.knowledge import status as kstatus  # noqa: E402
from src.copilot.knowledge.router import (  # noqa: E402
    detect_country,
    route_question,
    source_priority,
)

OUT = Path("evaluations/knowledge_expansion")


def _load(name: str) -> dict:
    with open(OUT / name, encoding="utf-8") as handle:
        return json.load(handle)


def evaluate_routing() -> tuple[list[dict], float]:
    cases = _load("routing_cases.json")["cases"]
    rows, correct = [], 0
    for c in cases:
        got = route_question(c["query"]).lane
        ok = got == c["expected_lane"]
        correct += ok
        rows.append({"id": c["id"], "query": c["query"],
                     "expected_lane": c["expected_lane"], "actual_lane": got, "correct": ok})
    return rows, (correct / len(cases) if cases else 0.0)


def evaluate_geo() -> tuple[list[dict], float]:
    cases = _load("geo_cases.json")["cases"]
    rows, correct = [], 0
    for c in cases:
        country = detect_country(c["query"])
        top = source_priority(country)[0] if source_priority(country) else None
        ok = (country == c["expected_country"]) and (top == c["expected_top_source"])
        correct += ok
        rows.append({"id": c["id"], "query": c["query"],
                     "expected_country": c["expected_country"], "actual_country": country,
                     "expected_top_source": c["expected_top_source"], "actual_top_source": top,
                     "correct": ok})
    return rows, (correct / len(cases) if cases else 0.0)


def evaluate_coverage() -> tuple[list[dict], dict]:
    entries = {e.source_id: e for e in km.load_manifest(constants.SOURCE_MANIFEST_PATH)}
    statuses = kstatus.compute_status(constants.SOURCE_MANIFEST_PATH)
    rows = []
    for s in statuses:
        e = entries.get(s.source_id)
        rows.append({
            "source_id": s.source_id,
            "group": e.group if e else "",
            "authority": e.authority_level if e else "",
            "records": s.record_count,
            "lifecycle": s.lifecycle,
            "manual_acquisition": s.needs_manual_acquisition,
            "licence_review": s.needs_licence_review,
        })
    return rows, kstatus.summary(statuses)


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    routing_rows, routing_acc = evaluate_routing()
    geo_rows, geo_acc = evaluate_geo()
    coverage_rows, health = evaluate_coverage()

    _write_csv(OUT / "routing_results.csv", routing_rows)
    _write_csv(OUT / "geo_results.csv", geo_rows)
    _write_csv(OUT / "coverage.csv", coverage_rows)

    # Provenance completeness: every measured structured record has a source_id
    # (guaranteed by schema; report the measured structured total for the record).
    structured_records = health["structured_records"]

    md = []
    md.append("# Knowledge Expansion Evaluation (KB-2)\n")
    md.append("Offline, deterministic evaluation of the expanded authoritative "
              "career knowledge system. Does not modify the preserved 11R / 11R-A "
              "baseline artifacts.\n")
    md.append("## Coverage (measured)\n")
    md.append(f"- Configured sources: **{health['configured']}**")
    md.append(f"- Available for retrieval (loaded locally): **{health['available_locally']}**")
    md.append(f"- Acquired on disk: **{health['acquired']}**")
    md.append(f"- Manual acquisition required: **{health['manual_acquisition']}**")
    md.append(f"- Licence review required: **{health['licence_review']}**")
    md.append(f"- Structured records loaded: **{structured_records}**\n")
    md.append("Per-source lifecycle in `coverage.csv`.\n")
    md.append("## Routing accuracy\n")
    md.append(f"- Lane routing accuracy: **{routing_acc:.0%}** "
              f"({sum(r['correct'] for r in routing_rows)}/{len(routing_rows)})")
    md.append(f"- Geographic precedence accuracy: **{geo_acc:.0%}** "
              f"({sum(r['correct'] for r in geo_rows)}/{len(geo_rows)})\n")
    md.append("Per-case detail in `routing_results.csv` and `geo_results.csv`.\n")
    md.append("## Provenance\n")
    md.append("Every structured record carries a `source_id` by schema; every "
              "manifest source without a resolved licence is flagged for review or "
              "manual acquisition (verified in `tests/test_knowledge_expansion.py`).\n")
    md.append("## Method\n")
    md.append("- Routing: deterministic router over labelled cases (no LLM).")
    md.append("- Coverage/lifecycle: measured from local structured stores and the "
              "vector manifest — a configured source is never assumed loaded.")
    md.append("- No network or paid LLM calls.\n")

    (OUT / "results.md").write_text("\n".join(md), encoding="utf-8")

    print(f"Routing accuracy      : {routing_acc:.0%}")
    print(f"Geo precedence accuracy: {geo_acc:.0%}")
    print(f"Coverage available    : {health['available_locally']}/{health['configured']}")
    print(f"Structured records    : {structured_records}")
    print(f"Wrote results under {OUT}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
