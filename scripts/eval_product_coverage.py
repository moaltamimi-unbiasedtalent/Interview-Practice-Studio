"""Product-coverage benchmark runner (CI-PH4).

Answers: "Can Career Intelligence reliably support the questions a real candidate
asks while preparing for a role?" — measured over the production-ready REAL
structured sources (no synthetic-fixture-only coverage counts toward production).

Deterministic + offline: routing, occupation resolution, geographic source
correctness, evidence Hit@5, provenance/citation availability, salary context,
year correctness, tool selection, insufficient-evidence correctness, latency.
No LLM call is required; if no dedicated embedding key is set the run is labelled
lexical/offline (never called "semantic").

Writes: results.csv, summary.md, failures.md under evaluations/product_coverage/.
Does NOT touch the 11R / 11R-A / KB-2 artifacts.

Usage:  python scripts/eval_product_coverage.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.config import load_config  # noqa: E402
from src.copilot.knowledge.retrieval import build_default_coordinator  # noqa: E402
from src.copilot.knowledge.router import detect_country, route_question  # noqa: E402
from src.copilot.rag.routing import route_for_intent  # noqa: E402
from src.copilot.rag.translation import QueryTranslator  # noqa: E402

DIR = Path("evaluations/product_coverage")
GATES = {
    "routing": 0.95, "geo_source": 0.95, "evidence_hit@5": 0.90,
    "citation_validity": 1.00, "salary_context": 1.00, "tool_selection": 0.95,
    "insufficient_evidence": 0.95,
}


def _base(sid: str) -> str:
    return (sid or "").split(":", 1)[0]


def _embedding_mode(config) -> str:
    key = getattr(config, "embedding_api_key", None)
    provider = (getattr(config, "embedding_provider", "auto") or "auto").lower()
    if provider == "openai" or (provider == "auto" and key and key.get_secret_value().strip()):
        return "semantic (dedicated embedding key)"
    return "lexical/offline (local hash embedder)"


def run() -> dict:
    cases = json.loads((DIR / "cases.json").read_text(encoding="utf-8"))["cases"]
    config = load_config()
    coord = build_default_coordinator(config)
    # config=None forces the deterministic heuristic intent classifier — the
    # benchmark must never make live LLM calls.
    translator = QueryTranslator(config=None)
    mode = _embedding_mode(config)

    rows = []
    for c in cases:
        q = c["query"]
        t0 = time.perf_counter()
        decision = route_question(q)
        outcome = coord.retrieve(decision, q)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        ev = outcome.evidence
        exp_src = set(c["expected_source_family"] or [])
        srcs = {_base(e.source_id) for e in ev}
        # An ambiguous occupation → the product asks the user to clarify. That is a
        # valid, non-fabricating outcome, so it counts as handled (not a failure).
        clarified = bool(getattr(outcome, "clarify", False))
        handled = bool(ev) or c["insufficient_ok"] or clarified

        # --- metrics (None => not-applicable for this case) ---
        routing_ok = decision.lane in c["expected_lanes"]

        resolution_ok = None
        if c["resolution_expected"]:
            resolution_ok = bool(outcome.resolved and outcome.resolved.candidates)

        geo_ok = None
        if c["geography"]:
            det = detect_country(q)
            geo_ok = (det == c["geography"])
            if exp_src and ev:  # when we do have evidence, its source must be right geo
                geo_ok = geo_ok and bool(srcs & exp_src)

        # Hit@5 measures COVERAGE: right-source evidence, or an acceptable gap.
        if ev:
            hit_ok = bool(srcs & exp_src) if exp_src else True
        else:
            hit_ok = c["insufficient_ok"] or clarified

        # Citation / salary / year measure VALIDITY of produced evidence — only
        # applicable when the relevant evidence actually exists (coverage is
        # measured separately by hit@5), so a gap is not double-counted here.
        comp = [e for e in ev if e.evidence_type == "compensation"]
        dated = [e for e in ev if e.evidence_type in ("compensation", "forecast", "vacancy", "openings")]

        citation_ok = None
        if c["citation_required"] and ev:
            citation_ok = all(e.source_url for e in ev)

        provenance_ok = all(e.source_id for e in ev) if ev else None

        salary_ok = None
        if c["salary_context_required"] and comp:
            salary_ok = all(e.metadata.get("currency") and e.metadata.get("pay_period")
                            and e.reference_year for e in comp)

        year_ok = None
        if c["year_required"] and dated:
            year_ok = all(e.reference_year for e in dated)

        tool_ok = None
        if c["expected_tool"]:
            intent = translator.translate(q).intent
            tools = route_for_intent(intent).tools
            tool_ok = c["expected_tool"] in tools

        insuff_ok = handled

        unsupported_ok = None
        if c["question_family"] == "unsupported":
            unsupported_ok = (len(ev) == 0)  # never fabricates structured evidence

        rows.append({
            "id": c["id"], "question_family": c["question_family"],
            "occupation_family": c["occupation_family"], "geography": c["geography"] or "",
            "lane": decision.lane, "expected_lanes": "|".join(c["expected_lanes"]),
            "evidence": len(ev), "sources": "|".join(sorted(srcs)),
            "routing_ok": routing_ok, "resolution_ok": resolution_ok, "geo_ok": geo_ok,
            "hit@5_ok": hit_ok, "citation_ok": citation_ok, "provenance_ok": provenance_ok,
            "salary_ok": salary_ok, "year_ok": year_ok, "tool_ok": tool_ok,
            "insufficient_ok": insuff_ok, "unsupported_ok": unsupported_ok,
            "latency_ms": latency_ms,
        })
    return {"rows": rows, "mode": mode, "count": len(cases)}


def _rate(rows, key):
    vals = [r[key] for r in rows if r[key] is not None]
    return (sum(1 for v in vals if v) / len(vals), len(vals)) if vals else (None, 0)


def _categorise(r) -> str | None:
    """Primary failure category for a row (most upstream failure first)."""
    if r["routing_ok"] is False:
        return "routing"
    if r["resolution_ok"] is False:
        return "occupation_resolution"
    if r["geo_ok"] is False:
        return "geography"
    if r["hit@5_ok"] is False:
        return "missing_source" if not r["sources"] else "source_mismatch"
    if r["tool_ok"] is False:
        return "tool"
    if r["citation_ok"] is False:
        return "citation"
    if r["salary_ok"] is False or r["year_ok"] is False:
        return "data_quality"
    if r["insufficient_ok"] is False:
        return "retrieval"
    if r["unsupported_ok"] is False:
        return "llm_synthesis"
    return None


def write_reports(res: dict) -> None:
    rows = res["rows"]
    DIR.mkdir(parents=True, exist_ok=True)
    with open(DIR / "results.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    metrics = {
        "routing": _rate(rows, "routing_ok"),
        "occupation_resolution": _rate(rows, "resolution_ok"),
        "geo_source": _rate(rows, "geo_ok"),
        "evidence_hit@5": _rate(rows, "hit@5_ok"),
        "citation_validity": _rate(rows, "citation_ok"),
        "provenance_completeness": _rate(rows, "provenance_ok"),
        "salary_context": _rate(rows, "salary_ok"),
        "year_correctness": _rate(rows, "year_ok"),
        "tool_selection": _rate(rows, "tool_ok"),
        "insufficient_evidence": _rate(rows, "insufficient_ok"),
        "unsupported_claim": _rate(rows, "unsupported_ok"),
    }
    lat = sorted(r["latency_ms"] for r in rows)
    p50 = lat[len(lat) // 2]; p95 = lat[int(len(lat) * 0.95)]

    lines = ["# Product Coverage Benchmark\n",
             f"**{res['count']} labelled candidate questions** over the production-ready "
             "real career-knowledge sources. Deterministic run.",
             f"Embedding mode: **{res['mode']}**.\n",
             "Does not modify the 11R / 11R-A / KB-2 architecture benchmarks.\n",
             "## Metrics vs product gates\n",
             "| Metric | Score | n | Gate | Pass |", "|---|---|---|---|---|"]
    for k, (rate, n) in metrics.items():
        gate = GATES.get(k)
        rate_s = f"{rate:.0%}" if rate is not None else "n/a"
        gate_s = f"{gate:.0%}" if gate else "—"
        ok = "—" if (gate is None or rate is None) else ("✅" if rate >= gate else "❌")
        lines.append(f"| {k} | {rate_s} | {n} | {gate_s} | {ok} |")
    lines.append(f"\nLatency (structured retrieval): p50 {p50} ms · p95 {p95} ms.\n")

    # Coverage by question family.
    lines.append("## Coverage by question family\n")
    lines.append("| Question family | Cases | Routing | Covered (Hit@5 / gap-ok) |")
    lines.append("|---|---|---|---|")
    byfam = defaultdict(list)
    for r in rows:
        byfam[r["question_family"]].append(r)
    for fam in sorted(byfam):
        fr = byfam[fam]
        rt, _ = _rate(fr, "routing_ok")
        hv = [r["hit@5_ok"] for r in fr if r["hit@5_ok"] is not None]
        cov = (sum(1 for v in hv if v) / len(hv)) if hv else None
        lines.append(f"| {fam} | {len(fr)} | {rt:.0%} | {cov:.0%} |" if cov is not None
                     else f"| {fam} | {len(fr)} | {rt:.0%} | n/a |")

    # Coverage by geography.
    lines.append("\n## Coverage by geography\n")
    lines.append("| Geography | Cases | Geo-source correct | Covered |")
    lines.append("|---|---|---|---|")
    bygeo = defaultdict(list)
    for r in rows:
        if r["geography"]:
            bygeo[r["geography"]].append(r)
    for g in sorted(bygeo):
        gr = bygeo[g]
        gs, _ = _rate(gr, "geo_ok")
        hv = [r["hit@5_ok"] for r in gr if r["hit@5_ok"] is not None]
        cov = (sum(1 for v in hv if v) / len(hv)) if hv else 0
        lines.append(f"| {g} | {len(gr)} | {gs:.0%} | {cov:.0%} |")

    # Source routing usage.
    lines.append("\n## Source routing (evidence provenance)\n")
    src_counter = Counter()
    for r in rows:
        for s in filter(None, r["sources"].split("|")):
            src_counter[s] += 1
    for s, n in src_counter.most_common():
        lines.append(f"- `{s}` — {n} cases")
    (DIR / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Failures + ranked remediation.
    fails = [(r, _categorise(r)) for r in rows]
    fails = [(r, cat) for r, cat in fails if cat]
    cats = Counter(cat for _, cat in fails)
    flines = ["# Product Coverage — Failure Analysis\n",
              f"{len(fails)} of {len(rows)} cases have at least one failed applicable check.\n",
              "## Ranked remediation (by failing-case count)\n"]
    remedy = {
        "routing": "Tighten/extend router rules for these question phrasings.",
        "occupation_resolution": "Improve occupation resolver (aliases, crosswalks, disambiguation).",
        "geography": "Fix country detection / source precedence for the geography.",
        "missing_source": "Acquire a production source for this slice (no real data loaded).",
        "source_mismatch": "Correct the expected/actual source mapping for the lane.",
        "tool": "Fix intent→tool routing for this family.",
        "citation": "Ensure structured evidence carries a source_url.",
        "data_quality": "Backfill salary context / reference year on the records.",
        "retrieval": "Lane produced nothing where evidence was expected — check store/query.",
        "llm_synthesis": "Unsupported query leaked structured evidence — tighten guard.",
    }
    for cat, n in cats.most_common():
        flines.append(f"1. **{cat}** — {n} case(s). {remedy.get(cat, '')}")
    flines.append("\n## Failing cases\n")
    flines.append("| id | question_family | geo | category | lane | evidence |")
    flines.append("|---|---|---|---|---|---|")
    for r, cat in fails[:200]:
        flines.append(f"| {r['id']} | {r['question_family']} | {r['geography']} | {cat} | {r['lane']} | {r['evidence']} |")
    (DIR / "failures.md").write_text("\n".join(flines) + "\n", encoding="utf-8")


def main() -> int:
    res = run()
    write_reports(res)
    rows = res["rows"]
    print(f"Ran {res['count']} cases | mode: {res['mode']}")
    for k in ("routing", "geo_source", "evidence_hit@5", "citation_validity",
              "salary_context", "tool_selection", "insufficient_evidence"):
        rate, n = _rate(rows, {"geo_source": "geo_ok", "evidence_hit@5": "hit@5_ok",
                               "citation_validity": "citation_ok", "salary_context": "salary_ok",
                               "tool_selection": "tool_ok",
                               "insufficient_evidence": "insufficient_ok"}.get(k, k + "_ok")
                        if k != "routing" else "routing_ok")
        gate = GATES.get(k)
        flag = "" if (rate is None or gate is None) else (" OK" if rate >= gate else " BELOW GATE")
        print(f"  {k:22} {rate:.0%} (n={n}){flag}" if rate is not None else f"  {k:22} n/a")
    return 0


if __name__ == "__main__":
    sys.exit(main())
