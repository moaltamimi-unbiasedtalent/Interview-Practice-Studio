"""CI-PH4: validate the product-coverage benchmark dataset structure."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

CASES = Path("evaluations/product_coverage/cases.json")

REQUIRED_KEYS = {
    "id", "query", "expected_lanes", "occupation", "occupation_family",
    "question_family", "geography", "expected_source_family", "citation_required",
    "insufficient_ok", "expected_tool", "salary_context_required", "year_required",
    "resolution_expected",
}


@pytest.mark.skipif(not CASES.is_file(), reason="benchmark not generated")
class TestBenchmarkDataset:
    def _cases(self):
        return json.loads(CASES.read_text(encoding="utf-8"))["cases"]

    def test_at_least_300_cases(self) -> None:
        assert len(self._cases()) >= 300

    def test_every_case_has_required_labels(self) -> None:
        for c in self._cases():
            assert REQUIRED_KEYS <= set(c), f"{c['id']} missing keys"
            assert c["expected_lanes"] and isinstance(c["expected_lanes"], list)

    def test_covers_ten_occupation_and_many_question_families(self) -> None:
        cs = self._cases()
        assert len({c["occupation_family"] for c in cs}) >= 10
        assert len({c["question_family"] for c in cs}) >= 20

    def test_covers_four_geographies(self) -> None:
        geos = {c["geography"] for c in self._cases() if c["geography"]}
        assert {"US", "UK", "DE", "EU"} <= geos

    def test_unique_ids(self) -> None:
        ids = [c["id"] for c in self._cases()]
        assert len(ids) == len(set(ids))
