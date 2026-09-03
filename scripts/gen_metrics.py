"""Single source of current, measured Career-Intelligence metrics.

Aggregates source status, structured-store counts, vector chunks, the product
coverage run and the inventory into one place, and computes production readiness
per coverage area (READY / PARTIAL / MISSING). Writes:

  data/metrics.json          — machine-readable canonical metrics
  docs/metrics_snapshot.md   — human-readable current metrics (referenced by docs)

Every number is measured — no hardcoded counts. Historical 11R/11R-A results are
NOT touched (they live in their own preserved artifacts).

Usage:  python scripts/gen_metrics.py
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.knowledge import status as st  # noqa: E402

METRICS_JSON = Path("data/metrics.json")
SNAPSHOT_MD = Path("docs/metrics_snapshot.md")


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


def _origin_records(statuses):
    """{source_id: (record_count, data_origin, production_ready)}."""
    return {s.source_id: (s.record_count + s.chunk_count, s.data_origin, s.production_ready)
            for s in statuses}


def _readiness(statuses) -> list[dict]:
    """READY / PARTIAL / MISSING per coverage area, from measured data."""
    by = {s.source_id: s for s in statuses}
    R, _C, CO = constants.ROLE_DB_PATH, constants.COMPENSATION_DB_PATH, constants.COMPETENCY_DB_PATH
    LM, CR = constants.LABOUR_MARKET_DB_PATH, constants.CREDENTIAL_DB_PATH

    def real(sid) -> bool:
        s = by.get(sid)
        return bool(s and s.production_ready) or bool(
            s and s.data_origin in (constants.ORIGIN_OFFICIAL_LOCAL,
                                    constants.ORIGIN_OFFICIAL_DOWNLOAD,
                                    constants.ORIGIN_AUTHORISED_MANUAL,
                                    constants.ORIGIN_MIXED))

    def fixture(sid) -> bool:
        s = by.get(sid)
        return bool(s and s.fixture_only)

    def verdict(has_real, has_any, note=""):
        return {"status": "READY" if has_real else ("PARTIAL" if has_any else "MISSING"),
                "detail": note}

    tasks = _q(R, "SELECT COUNT(*) FROM occupation_tasks")
    skills = _q(R, "SELECT COUNT(*) FROM occupation_skills")
    techs = _q(R, "SELECT COUNT(*) FROM occupation_skills WHERE skill_type='technology'")
    edu = _q(R, "SELECT COUNT(*) FROM occupation_attributes WHERE attr_type='entry_education'")
    rels = _q(R, "SELECT COUNT(*) FROM occupation_relationships")
    certs = _q(CR, "SELECT COUNT(*) FROM certifications")
    lics = _q(CR, "SELECT COUNT(*) FROM occupational_licences")
    behaviours = _q(CO, "SELECT COUNT(*) FROM role_behaviours")
    vac = _q(LM, "SELECT COUNT(*) FROM labour_vacancies")

    real_occ = any(real(s) for s in ("onet", "esco", "isco08", "kldb", "bls_ooh"))
    areas = [
        ("roles", verdict(real_occ, real_occ, "O*NET/ESCO/ISCO/KldB/BLS OOH")),
        ("responsibilities", verdict(real_occ and tasks > 0, tasks > 0, f"{tasks:,} task rows")),
        ("skills", verdict(real_occ and skills > 0, skills > 0, f"{skills:,} skill rows")),
        ("technologies", verdict(techs > 0, techs > 0, f"{techs:,} technology rows")),
        ("education", verdict(edu > 0, edu > 0, f"{edu:,} entry-education rows (BLS)")),
        ("certifications", verdict(False, certs > 0, "sample only — CareerOneStop not loaded")),
        ("licences", verdict(False, lics > 0, "sample only — CareerOneStop not loaded")),
        ("seniority", verdict(False, behaviours > 0, "Civil Service behaviours (sample)")),
        ("US compensation", verdict(real("bls_oews"), real("bls_oews"), "BLS OEWS")),
        ("UK compensation", verdict(real("ons_ashe"), real("ons_ashe"), "ONS ASHE")),
        ("DE compensation", verdict(False, False, "Entgeltatlas not loaded")),
        ("EU compensation", verdict(False, False, "no structured EU pay source loaded")),
        ("long-term outlook", verdict(real("bls_projections"), real("bls_projections"),
                                      "BLS Employment Projections (US)")),
        ("short-term outlook", verdict(False, edu > 0 or vac > 0, "derived from outlook attributes")),
        ("vacancies", verdict(real("eurostat_occ_vacancy"), vac > 0,
                              "Eurostat JVS — country-level (ISCO Total)")),
        ("shortages", verdict(real("cedefop_clssi"), real("cedefop_clssi") or fixture("cedefop_shortage_index"),
                              "Cedefop CLSSI (group-level)")),
        ("career transitions", verdict(rels > 0, rels > 0, f"{rels:,} occupation relationships")),
        ("digital skills", verdict(real("digcomp"), True, "DigComp 2.2 (ESCO mapping)")),
        ("cybersecurity", verdict(real("nice_framework"), True, "NICE Framework v2.2.0")),
        ("company context", {"status": "READY", "detail": "capability (user-supplied, time-stamped)"}),
    ]
    # vacancies is real but country-level → mark PARTIAL not READY (granularity).
    for a in areas:
        if a[0] == "vacancies" and a[1]["status"] == "READY":
            a[1]["status"] = "PARTIAL"
    return [{"area": a, **v} for a, v in areas]


def _coverage_metrics() -> dict:
    path = "evaluations/product_coverage/results.csv"
    if not os.path.isfile(path):
        return {}
    rows = list(csv.DictReader(open(path, encoding="utf-8")))

    def rate(key):
        vals = [r[key] for r in rows if r[key] not in ("", "None")]
        return round(sum(1 for v in vals if v == "True") / len(vals), 4) if vals else None

    return {"cases": len(rows),
            "routing": rate("routing_ok"), "geo_source": rate("geo_ok"),
            "evidence_hit@5": rate("hit@5_ok"), "citation_validity": rate("citation_ok"),
            "salary_context": rate("salary_ok"), "tool_selection": rate("tool_ok"),
            "insufficient_evidence": rate("insufficient_ok")}


def build_metrics() -> dict:
    statuses = st.compute_status()
    health = st.summary(statuses)
    R, C = constants.ROLE_DB_PATH, constants.COMPENSATION_DB_PATH
    CO, LM, CR = (constants.COMPETENCY_DB_PATH, constants.LABOUR_MARKET_DB_PATH,
                  constants.CREDENTIAL_DB_PATH)
    stores = {
        "occupations": _q(R, "SELECT COUNT(*) FROM occupations"),
        "occupation_tasks": _q(R, "SELECT COUNT(*) FROM occupation_tasks"),
        "occupation_skills": _q(R, "SELECT COUNT(*) FROM occupation_skills"),
        "competencies": _q(CO, "SELECT COUNT(*) FROM competencies"),
        "compensation": _q(C, "SELECT COUNT(*) FROM compensation_records"),
        "labour_market": sum(_q(LM, f"SELECT COUNT(*) FROM {t}") for t in
                             ("labour_market_forecasts", "labour_market_openings",
                              "labour_shortages", "labour_vacancies")),
        "credentials": _q(CR, "SELECT COUNT(*) FROM certifications") + _q(CR, "SELECT COUNT(*) FROM occupational_licences"),
    }
    inv_path = "data/source_inventory.json"
    inv = json.load(open(inv_path, encoding="utf-8")) if os.path.isfile(inv_path) else {}
    return {
        "generated": "on-demand",
        "sources": {
            "configured": health["configured"],
            "retrieval_ready": health["available_locally"],
            "production_ready": health["production_ready"],
            "real_data_sources": health["real_data_sources"],
            "fixture_only": health["fixture_only"],
            "manual_acquisition_outstanding": health["manual_acquisition"],
            "licence_review_outstanding": health["licence_review"],
        },
        "records": {
            "structured_total": health["structured_records"],
            "vector_chunks": health["vector_chunks"],
            **stores,
        },
        "inventory": {
            "files": inv.get("file_count", 0),
            "unresolved": inv.get("unresolved_count", 0),
            "sources_found_local": len(inv.get("source_ids_found", [])),
        },
        "coverage_benchmark": _coverage_metrics(),
        "readiness_by_area": _readiness(statuses),
    }


def _snapshot_md(m: dict) -> str:
    s, r, cov = m["sources"], m["records"], m.get("coverage_benchmark", {})
    L = ["# Current Metrics Snapshot\n",
         "Generated by `python scripts/gen_metrics.py` — the single source of "
         "current measured numbers referenced by the other docs. Regenerate after "
         "rebuilding the knowledge base. (Historical 11R/11R-A results are separate.)\n",
         "## Sources\n",
         f"- Configured: **{s['configured']}**",
         f"- Retrieval-ready: **{s['retrieval_ready']}**",
         f"- Production-ready (real + clear licence): **{s['production_ready']}**",
         f"- Real-data sources: **{s['real_data_sources']}** · Fixture-only: **{s['fixture_only']}**",
         f"- Manual-acquisition outstanding: **{s['manual_acquisition_outstanding']}** · "
         f"Licence-review outstanding: **{s['licence_review_outstanding']}**\n",
         "## Records\n",
         f"- Structured records: **{r['structured_total']:,}** · Vector chunks: **{r['vector_chunks']:,}**",
         f"- Occupations {r['occupations']:,} · tasks {r['occupation_tasks']:,} · "
         f"skills {r['occupation_skills']:,} · competencies {r['competencies']:,} · "
         f"compensation {r['compensation']:,} · labour-market {r['labour_market']:,} · "
         f"credentials {r['credentials']:,}\n"]
    if cov:
        L.append("## Product coverage benchmark (offline)\n")
        L.append(f"- {cov.get('cases', 0)} cases — routing "
                 f"{_pct(cov.get('routing'))}, geo-source {_pct(cov.get('geo_source'))}, "
                 f"Hit@5 {_pct(cov.get('evidence_hit@5'))}, citation "
                 f"{_pct(cov.get('citation_validity'))}, salary-context "
                 f"{_pct(cov.get('salary_context'))}, tool {_pct(cov.get('tool_selection'))}, "
                 f"insufficient {_pct(cov.get('insufficient_evidence'))}\n")
    L.append("## Production readiness by coverage area\n")
    L.append("| Area | Status | Detail |")
    L.append("|---|---|---|")
    for a in m["readiness_by_area"]:
        L.append(f"| {a['area']} | {a['status']} | {a['detail']} |")
    L.append("")
    return "\n".join(L)


def _pct(v):
    return f"{v:.0%}" if isinstance(v, (int, float)) else "n/a"


def main() -> int:
    m = build_metrics()
    METRICS_JSON.parent.mkdir(parents=True, exist_ok=True)
    METRICS_JSON.write_text(json.dumps(m, indent=2), encoding="utf-8")
    SNAPSHOT_MD.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_MD.write_text(_snapshot_md(m), encoding="utf-8")
    {a["status"] for a in m["readiness_by_area"]}
    print(f"Wrote {METRICS_JSON} and {SNAPSHOT_MD}")
    print(f"Sources: {m['sources']}")
    print(f"Readiness areas: {len(m['readiness_by_area'])} "
          f"(READY {sum(1 for a in m['readiness_by_area'] if a['status']=='READY')}, "
          f"PARTIAL {sum(1 for a in m['readiness_by_area'] if a['status']=='PARTIAL')}, "
          f"MISSING {sum(1 for a in m['readiness_by_area'] if a['status']=='MISSING')})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
