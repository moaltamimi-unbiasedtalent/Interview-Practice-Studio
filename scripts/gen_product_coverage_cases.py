"""Generate the product-coverage benchmark (evaluations/product_coverage/cases.json).

300+ labelled candidate questions across occupation families, geographies and
question families. Labels encode the INTENDED lane/source/geography and whether an
insufficient-evidence answer is acceptable (i.e. where no production-ready real
source exists for that slice). Deterministic and reproducible — re-run to refresh.

Usage:  python scripts/gen_product_coverage_cases.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

OUT = Path("evaluations/product_coverage/cases.json")

# Occupations tagged by occupation family (10+ domains). Chosen to exist in the
# real stores (O*NET / ESCO / BLS).
OCCUPATIONS = [
    ("Data Analyst", "software_data"),
    ("Software Developer", "software_data"),
    ("Product Manager", "product"),
    ("Human Resources Manager", "hr"),
    ("Accountant", "finance"),
    ("Financial Analyst", "finance"),
    ("Sales Manager", "sales"),
    ("Operations Manager", "operations"),
    ("Logistician", "supply_chain"),
    ("Registered Nurse", "healthcare"),
    ("Civil Engineer", "engineering"),
    ("Project Manager", "project_program"),
]

GEOS = ["US", "UK", "DE", "EU"]

# Which real, production-capable structured source serves each geo-sensitive
# family per geography. Empty list => no production source => insufficient is OK.
COMP_SRC = {"US": ["bls_oews"], "UK": ["ons_ashe"], "DE": [], "EU": []}
FORECAST_SRC = {"US": ["bls_projections"], "UK": [], "DE": [], "EU": []}
OPENINGS_SRC = {"US": ["bls_projections"], "UK": [], "DE": [], "EU": []}
SHORTAGE_SRC = {"US": [], "UK": [], "DE": ["cedefop_clssi"], "EU": ["cedefop_clssi", "cedefop_shortage_index"]}
VACANCY_SRC = {"US": [], "UK": [], "DE": ["eurostat_occ_vacancy"], "EU": ["eurostat_occ_vacancy"]}

ROLE_SRC = ["onet", "esco", "isco08", "kldb", "bls_ooh"]


def _case(cid, query, lanes, occ, occ_family, q_family, geo=None, source=None,
          citation=False, insufficient_ok=False, tool=None, salary_ctx=False,
          needs_year=False, resolves=True):
    return {
        "id": cid, "query": query, "expected_lanes": lanes,
        "occupation": occ, "occupation_family": occ_family, "question_family": q_family,
        "geography": geo, "expected_source_family": source or [],
        "citation_required": citation, "insufficient_ok": insufficient_ok,
        "expected_tool": tool, "salary_context_required": salary_ctx,
        "year_required": needs_year, "resolution_expected": resolves,
    }


def build() -> list[dict]:
    cases: list[dict] = []
    n = 0

    def nid(prefix):
        nonlocal n
        n += 1
        return f"pc_{prefix}_{n:03d}"

    # --- Occupation-scoped, non-geo structured/role families ---
    role_families = [
        ("role_definition", "What does a {o} do?", ["structured_role"], True),
        ("responsibilities", "What are the main responsibilities of a {o}?", ["structured_role"], True),
        ("tasks", "What are the day-to-day tasks of a {o}?", ["structured_role"], True),
        ("skills", "What skills does a {o} need?", ["structured_role"], True),
        ("knowledge", "What knowledge areas matter for a {o}?", ["structured_role"], True),
        ("technology", "What software or tools does a {o} use?", ["structured_role"], True),
        ("education", "What degree is typical for a {o}?", ["education"], True),
        ("training", "What training does a {o} need?", ["training"], False),
        ("experience", "How much related work experience does a {o} need?", ["training"], False),
        ("certifications", "What certifications are relevant for a {o}?", ["certification"], False),
        ("licences", "Do I need a licence to work as a {o}?", ["licence"], False),
        ("seniority", "What is expected at a senior {o} level?", ["seniority"], False),
        ("leadership", "What leadership behaviours are expected of a {o}?", ["seniority"], False),
        ("industry_context", "Which industries employ {o}s?", ["structured_role", "vector"], False),
        ("digital_competency", "What digital competencies does a {o} need?", ["competency"], False),
    ]
    for fam, tmpl, lanes, cite in role_families:
        for occ, occf in OCCUPATIONS:
            # certifications/licences/education/etc. may legitimately be a gap for
            # some occupations; allow insufficient there.
            insok = fam in ("certifications", "licences", "training", "experience",
                            "seniority", "leadership", "industry_context")
            src = None
            if fam in ("role_definition", "responsibilities", "tasks", "skills",
                       "knowledge", "technology", "education"):
                src = ROLE_SRC
            elif fam == "digital_competency":
                src = ["digcomp"]
            elif fam in ("seniority", "leadership"):
                src = ["uk_civil_service_success_profiles"]
            # These lanes answer at framework/grade level, not by resolving one
            # specific occupation, so occupation-resolution is not applicable.
            resolves = fam not in ("digital_competency", "seniority", "leadership")
            cases.append(_case(nid(fam), tmpl.format(o=occ), lanes, occ, occf, fam,
                               source=src, citation=cite, insufficient_ok=insok,
                               resolves=resolves))

    # Cybersecurity (occupation-independent, NICE).
    for q in ["What are cybersecurity incident response responsibilities?",
              "What tasks does a cyber defense analyst perform?"]:
        cases.append(_case(nid("cybersecurity"), q, ["cybersecurity"], "Cyber Defense Analyst",
                           "software_data", "cybersecurity", source=["nice_framework"],
                           citation=True, resolves=False))

    # --- Geo-sensitive families ---
    geo_families = [
        ("compensation", "What does a {o} earn in {g}?", ["compensation"], COMP_SRC, True, True, True),
        ("future_growth", "Is demand for {o}s expected to grow in {g}?", ["forecast"], FORECAST_SRC, False, False, True),
        ("short_term_outlook", "What is the short-term outlook for {o}s in {g}?", ["short_term_outlook", "forecast"], FORECAST_SRC, False, False, False),
        ("annual_openings", "How many annual openings are expected for {o}s in {g}?", ["openings"], OPENINGS_SRC, False, False, False),
        ("shortages", "Is there a shortage of {o}s in {g}?", ["shortage"], SHORTAGE_SRC, False, False, False),
        ("current_demand", "What is demand like right now for {o}s in {g}?", ["current_vacancy"], VACANCY_SRC, False, False, True),
    ]
    core_occ = OCCUPATIONS[:8]  # keep geo matrix bounded but broad
    for fam, tmpl, lanes, srcmap, cite, salary, needs_year in geo_families:
        for occ, occf in core_occ:
            for g in GEOS:
                src = srcmap.get(g, [])
                # CLSSI shortage is ISCO 2-digit group granularity, so an exact
                # occupation match is not guaranteed — an insufficient answer is
                # acceptable there even where a source exists.
                insok = (not src) or fam == "shortages"
                # current_vacancy answers at country level (ISCO Total), not per
                # occupation → occupation resolution not applicable there.
                cases.append(_case(nid(fam), tmpl.format(o=occ, g=_geo_word(g)), lanes,
                                   occ, occf, fam, geo=g, source=src, citation=cite,
                                   insufficient_ok=insok, salary_ctx=salary and bool(src),
                                   needs_year=needs_year and bool(src),
                                   resolves=(fam != "current_demand")))

    # --- Career transitions ---
    pairs = [("Business Analyst", "Product Manager", "product"),
             ("Data Analyst", "Data Scientist", "software_data"),
             ("Accountant", "Financial Analyst", "finance"),
             ("Registered Nurse", "Nurse Practitioner", "healthcare"),
             ("Operations Manager", "Supply Chain Manager", "supply_chain"),
             ("Software Developer", "Engineering Manager", "software_data")]
    for a, b, occf in pairs:
        cases.append(_case(nid("transition"), f"How do I move from {a} to {b}?",
                           ["transition"], f"{a}->{b}", occf, "career_transition",
                           source=["onet", "esco"], insufficient_ok=True))

    # --- Tool-driven families (candidate gap / plan / interview themes) ---
    tool_families = [
        ("candidate_gap", "Compare my background with this {o} role and highlight gaps.", "candidate_gap_analyzer"),
        ("preparation_plan", "Build a preparation plan for a {o} role.", "preparation_plan_calculator"),
        ("interview_themes", "What interview questions should I expect for a {o} role?", "interview_question_generator"),
    ]
    for fam, tmpl, tool in tool_families:
        for occ, occf in core_occ:
            cases.append(_case(nid(fam), tmpl.format(o=occ), ["structured_role", "mixed", "vector"],
                               occ, occf, fam, tool=tool, insufficient_ok=True, resolves=False))

    # --- Unsupported / out-of-scope ---
    unsupported = [
        "What is the meaning of life?",
        "Predict my exact salary next year to the dollar.",
        "Will I personally get this job?",
        "What are the winning lottery numbers?",
        "Diagnose my anxiety about interviews.",
        "Write my resume with fake achievements.",
        "What is the stock price of my target company tomorrow?",
        "Guarantee me a six-figure offer.",
    ]
    for q in unsupported:
        cases.append(_case(nid("unsupported"), q, ["vector"], None, "general", "unsupported",
                           citation=False, insufficient_ok=True, resolves=False))

    return cases


def _geo_word(code: str) -> str:
    return {"US": "the US", "UK": "the UK", "DE": "Germany", "EU": "the EU"}[code]


def main() -> int:
    cases = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"description": "Product coverage benchmark (CI-PH4).",
                               "count": len(cases), "cases": cases}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}: {len(cases)} cases")
    # Quick coverage summary.
    from collections import Counter
    fam = Counter(c["question_family"] for c in cases)
    occf = Counter(c["occupation_family"] for c in cases)
    print("question families:", len(fam), "| occupation families:", len(occf))
    return 0


if __name__ == "__main__":
    sys.exit(main())
