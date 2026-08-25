"""Phase 11R-A tests: evaluation hooks for the expanded architecture (offline).

Uses the committed synthetic samples + labelled datasets; never runs or touches
the preserved 11R benchmark artifacts.
"""

import csv
import json

from src.copilot import constants
from src.copilot.evaluation.expanded_eval import (
    CompensationCase,
    compare_to_baseline,
    evaluate_compensation,
    evaluate_router,
    evaluate_structured_role,
    load_baseline_retrieval,
    load_compensation_cases,
    load_role_cases,
    load_router_cases,
    provenance_completeness,
)
from src.copilot.knowledge import manifest as km
from src.copilot.knowledge import normalisers as norm
from src.copilot.knowledge.compensation import CompensationRecord, CompensationRepository
from src.copilot.knowledge.roles import RoleRepository

SAMPLES = "evaluations/knowledge_samples"
MANIFEST = km.load_manifest(constants.SOURCE_MANIFEST_PATH)


def _role_repo() -> RoleRepository:
    repo = RoleRepository(":memory:")
    for row in json.load(open(f"{SAMPLES}/roles_onet.json")):
        repo.add_occupation(norm.normalise_onet(row))
    for row in json.load(open(f"{SAMPLES}/roles_esco.json")):
        repo.add_occupation(norm.normalise_esco(row))
    for occ in norm.normalise_isco(json.load(open(f"{SAMPLES}/isco.json"))):
        repo.add_occupation(occ)
    return repo


def _comp_repo() -> CompensationRepository:
    repo = CompensationRepository(":memory:")
    with open(f"{SAMPLES}/compensation.csv", newline="") as h:
        for row in csv.DictReader(h):
            row = {k: (v or None) for k, v in row.items()}
            row["year"] = int(row["year"])
            for f in ("value", "lower_bound", "upper_bound"):
                row[f] = float(row[f]) if row[f] else None
            repo.add(CompensationRecord(**row))
    return repo


# --- Router ------------------------------------------------------------------


class TestRouterEval:
    def test_routing_accuracy(self) -> None:
        result = evaluate_router(load_router_cases("evaluations/router_cases.json"))
        assert result["accuracy"] == 1.0  # deterministic router matches labels
        assert set(result["by_lane"]) >= {"structured_role", "compensation", "forecast", "mixed", "vector"}


# --- Structured role ---------------------------------------------------------


class TestStructuredRoleEval:
    def test_hit_rate_and_provenance(self) -> None:
        result = evaluate_structured_role(
            _role_repo(), load_role_cases("evaluations/structured_role_cases.json"), MANIFEST
        )
        assert result["hit_rate"] == 1.0
        assert result["provenance_completeness"] == 1.0
        assert result["avg_latency_ms"] >= 0.0


# --- Compensation ------------------------------------------------------------


class TestCompensationEval:
    def test_accuracy_and_provenance(self) -> None:
        result = evaluate_compensation(
            _comp_repo(), load_compensation_cases("evaluations/compensation_cases.json"), MANIFEST
        )
        assert result["accuracy"] == 1.0
        assert result["provenance_completeness"] == 1.0

    def test_wrong_year_is_not_correct(self) -> None:
        repo = _comp_repo()
        bad = [CompensationCase(id="x", title="Data Analyst", country="US", year=1999,
                                expected_currency="USD", expected_statistic="median",
                                expected_source="bls_oews")]
        assert evaluate_compensation(repo, bad, MANIFEST)["accuracy"] == 0.0

    def test_wrong_country_is_not_correct(self) -> None:
        repo = _comp_repo()
        bad = [CompensationCase(id="x", title="Data Analyst", country="FR", year=2023,
                                expected_currency="EUR", expected_statistic="median",
                                expected_source="eurostat_earnings")]
        assert evaluate_compensation(repo, bad, MANIFEST)["accuracy"] == 0.0


# --- Provenance completeness -------------------------------------------------


class TestProvenance:
    def test_completeness_fraction(self) -> None:
        complete = {"source_id": "onet", "source_title": "O*NET", "publisher": "DOL",
                    "source_type": "occupation_taxonomy", "authority_level": 1}
        assert provenance_completeness([complete, None]) == 0.5
        assert provenance_completeness([complete]) == 1.0
        assert provenance_completeness([]) == 0.0


# --- Baseline comparison -----------------------------------------------------


class TestBaselineComparison:
    def test_load_and_compare(self) -> None:
        baseline = load_baseline_retrieval("evaluations/retrieval_results.csv")
        assert {"vector", "keyword", "hybrid"} <= set(baseline)
        # Same numbers → zero diff (expanded architecture does not alter narrative RAG).
        diffs = compare_to_baseline(baseline, baseline)
        assert all(v == 0.0 for mode in diffs.values() for v in mode.values())

    def test_compare_math(self) -> None:
        base = {"vector": {"mrr": 0.80, "hit_rate@k": 0.90}}
        cur = {"vector": {"mrr": 0.85, "hit_rate@k": 0.90}}
        diffs = compare_to_baseline(base, cur)
        assert diffs["vector"]["mrr"] == 0.05
        assert diffs["vector"]["hit_rate@k"] == 0.0
