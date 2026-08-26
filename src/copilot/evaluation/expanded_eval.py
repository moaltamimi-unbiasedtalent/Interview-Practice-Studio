"""Evaluation hooks for the expanded (multi-lane) Career Intelligence architecture.

These are *hooks* — deterministic evaluator functions and dataset loaders for the
new lanes (router, structured role, compensation) plus provenance completeness
and a baseline-comparison helper. They do not run or overwrite the 11R benchmark;
a later phase runs them and writes the expanded reports.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

__all__ = [
    "RouterCase", "evaluate_router",
    "StructuredRoleCase", "evaluate_structured_role",
    "CompensationCase", "evaluate_compensation",
    "provenance_completeness", "provenance_from_manifest",
    "compare_to_baseline", "load_baseline_retrieval",
    "load_router_cases", "load_role_cases", "load_compensation_cases",
]

# Required provenance fields for a "complete" structured/compensation citation.
_REQUIRED_PROVENANCE = ("source_id", "source_title", "publisher", "source_type", "authority_level")


# --- Router ------------------------------------------------------------------


@dataclass
class RouterCase:
    id: str
    query: str
    expected_lane: str


def evaluate_router(cases: list[RouterCase], llm_classifier=None) -> dict:
    """Overall + per-category routing accuracy using the deterministic router."""
    from src.copilot.knowledge.router import route_question

    correct = 0
    by_lane: dict[str, dict] = {}
    details = []
    for case in cases:
        got = route_question(case.query, llm_classifier=llm_classifier).lane
        ok = got == case.expected_lane
        correct += 1 if ok else 0
        bucket = by_lane.setdefault(case.expected_lane, {"correct": 0, "total": 0})
        bucket["total"] += 1
        bucket["correct"] += 1 if ok else 0
        details.append({"id": case.id, "expected": case.expected_lane, "got": got, "correct": ok})
    total = len(cases) or 1
    return {
        "accuracy": round(correct / total, 3),
        "correct": correct,
        "total": len(cases),
        "by_lane": {k: round(v["correct"] / v["total"], 3) for k, v in by_lane.items()},
        "details": details,
    }


# --- Provenance --------------------------------------------------------------


def provenance_from_manifest(source_id: str, entries) -> dict | None:
    """Build a provenance dict for a source_id from manifest entries."""
    for e in entries:
        if e.source_id == source_id:
            return {
                "source_id": e.source_id,
                "source_title": e.title,
                "publisher": e.publisher,
                "source_type": e.source_type,
                "authority_level": e.authority_level,
                "reference_year": e.reference_year,
                "country": e.country,
            }
    return None


def provenance_completeness(provenances: list[dict | None]) -> float:
    """Fraction of provenance records with all required fields present."""
    if not provenances:
        return 0.0
    complete = 0
    for p in provenances:
        if p and all(p.get(f) not in (None, "") for f in _REQUIRED_PROVENANCE):
            complete += 1
    return round(complete / len(provenances), 3)


# --- Structured role ---------------------------------------------------------


@dataclass
class StructuredRoleCase:
    id: str
    kind: str  # exact_title | alternate_title | occupation_code | related_occupation | skill_lookup | task_lookup | mapping
    query: str
    expected_code: str
    expected_source: str | None = None
    expected_extra: str | None = None  # related code / skill / task / mapping code


def evaluate_structured_role(repo, cases: list[StructuredRoleCase], manifest_entries=None) -> dict:
    """Hit rate, correct resolution, provenance completeness and latency."""
    hits = 0
    latency = 0.0
    provs: list[dict | None] = []
    details = []
    for case in cases:
        started = time.perf_counter()
        ok = _resolve_role(repo, case)
        latency += (time.perf_counter() - started) * 1000.0
        hits += 1 if ok else 0
        occ = repo.get_occupation(case.expected_code)
        if occ and manifest_entries is not None:
            provs.append(provenance_from_manifest(occ.get("source_id"), manifest_entries))
        details.append({"id": case.id, "kind": case.kind, "correct": ok})
    n = len(cases) or 1
    return {
        "cases": len(cases),
        "hit_rate": round(hits / n, 3),
        "provenance_completeness": provenance_completeness(provs) if provs else 0.0,
        "avg_latency_ms": round(latency / n, 3),
        "details": details,
    }


def _resolve_role(repo, case: StructuredRoleCase) -> bool:
    kind = case.kind
    if kind in ("exact_title", "alternate_title"):
        return any(r["occupation_code"] == case.expected_code for r in repo.search(case.query))
    if kind == "occupation_code":
        occ = repo.get_occupation(case.query)
        return bool(occ and occ["occupation_code"] == case.expected_code)
    occ = repo.get_occupation(case.expected_code)
    if not occ:
        return False
    if kind == "related_occupation":
        return any(r["related_code"] == case.expected_extra for r in occ.get("relationships", []))
    if kind == "skill_lookup":
        return any((s["skill"] or "").lower() == (case.expected_extra or "").lower()
                   for s in occ.get("skills", []))
    if kind == "task_lookup":
        return any((case.expected_extra or "").lower() in (t or "").lower()
                   for t in occ.get("tasks", []))
    if kind == "mapping":
        return any(m["code"] == case.expected_extra for m in occ.get("mappings", []))
    return False


# --- Compensation ------------------------------------------------------------


@dataclass
class CompensationCase:
    id: str
    title: str
    country: str
    year: int
    expected_currency: str
    expected_statistic: str
    expected_source: str


def evaluate_compensation(repo, cases: list[CompensationCase], manifest_entries=None) -> dict:
    """Correct only when country + year + currency + statistic + source all match."""
    correct = 0
    provs: list[dict | None] = []
    details = []
    for case in cases:
        records = repo.filter(country=case.country, year=case.year, title=case.title)
        match = next(
            (r for r in records
             if r.currency == case.expected_currency
             and r.statistic_type == case.expected_statistic
             and r.source_id == case.expected_source
             and r.country.lower() == case.country.lower()
             and r.year == case.year),
            None,
        )
        correct += 1 if match else 0
        if match and manifest_entries is not None:
            provs.append(provenance_from_manifest(match.source_id, manifest_entries))
        details.append({"id": case.id, "correct": bool(match)})
    n = len(cases) or 1
    return {
        "cases": len(cases),
        "accuracy": round(correct / n, 3),
        "provenance_completeness": provenance_completeness(provs) if provs else 0.0,
        "details": details,
    }


# --- Baseline comparison -----------------------------------------------------


def load_baseline_retrieval(path: str) -> dict[str, dict]:
    """Load the preserved 11R retrieval_results.csv into {mode: metrics}."""
    import csv

    out: dict[str, dict] = {}
    with open(path, encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("group") == "retrieval":
                out[row["mode"]] = {
                    "hit_rate@k": float(row["hit_rate@k"]),
                    "mrr": float(row["mrr"]),
                    "recall@k": float(row["recall@k"]),
                }
    return out


def compare_to_baseline(baseline: dict[str, dict], current: dict[str, dict]) -> dict:
    """Per-mode metric differences (current - baseline). Regressions are negative."""
    diffs: dict[str, dict] = {}
    for mode, cur in current.items():
        base = baseline.get(mode)
        if not base:
            continue
        diffs[mode] = {k: round(cur[k] - base[k], 3) for k in cur if k in base}
    return diffs


# --- Dataset loaders ---------------------------------------------------------


def load_router_cases(path: str) -> list[RouterCase]:
    with open(path, encoding="utf-8") as h:
        return [RouterCase(**c) for c in json.load(h)["cases"]]


def load_role_cases(path: str) -> list[StructuredRoleCase]:
    with open(path, encoding="utf-8") as h:
        return [StructuredRoleCase(**c) for c in json.load(h)["cases"]]


def load_compensation_cases(path: str) -> list[CompensationCase]:
    with open(path, encoding="utf-8") as h:
        return [CompensationCase(**c) for c in json.load(h)["cases"]]
