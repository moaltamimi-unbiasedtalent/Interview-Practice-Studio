"""OPT-8: deterministic source freshness computation."""

from __future__ import annotations

from src.copilot.knowledge import status as S


class TestComputeFreshness:
    def test_missing_year_is_unknown(self) -> None:
        assert S.compute_freshness(None, "annual", 2026) == S.FRESHNESS_UNKNOWN

    def test_undefined_cadence_is_unknown(self) -> None:
        # "periodic"/"rare" have no defined interval → never assert staleness.
        assert S.compute_freshness(2010, "periodic", 2026) == S.FRESHNESS_UNKNOWN
        assert S.compute_freshness(2010, "rare", 2026) == S.FRESHNESS_UNKNOWN
        assert S.compute_freshness(2010, None, 2026) == S.FRESHNESS_UNKNOWN

    def test_recent_annual_is_current(self) -> None:
        assert S.compute_freshness(2025, "annual", 2026) == S.FRESHNESS_CURRENT
        assert S.compute_freshness(2026, "annual", 2026) == S.FRESHNESS_CURRENT

    def test_old_annual_is_refresh_due(self) -> None:
        assert S.compute_freshness(2020, "annual", 2026) == S.FRESHNESS_DUE

    def test_biennial_tolerance(self) -> None:
        assert S.compute_freshness(2023, "biennial", 2026) == S.FRESHNESS_CURRENT  # age 3 ok
        assert S.compute_freshness(2021, "biennial", 2026) == S.FRESHNESS_DUE      # age 5

    def test_future_reference_year_is_current(self) -> None:
        assert S.compute_freshness(2027, "annual", 2026) == S.FRESHNESS_CURRENT


class TestStatusIntegration:
    def test_freshness_only_for_available_sources(self) -> None:
        statuses = S.compute_status(current_year=2026)
        for s in statuses:
            if not s.available_for_retrieval:
                assert s.freshness == S.FRESHNESS_UNKNOWN

    def test_summary_reports_freshness_counts(self) -> None:
        summary = S.summary(S.compute_status(current_year=2026))
        for key in ("fresh_current", "refresh_due", "freshness_unknown"):
            assert key in summary and isinstance(summary[key], int)
