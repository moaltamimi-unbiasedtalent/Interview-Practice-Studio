"""OPT-5: dry-run pipeline plan (deterministic, no LLM / retrieval / tools)."""

from __future__ import annotations

from src.copilot.config import CopilotConfig
from src.copilot.service import CareerIntelligenceService, PipelinePlan


def _svc():
    return CareerIntelligenceService(config=CopilotConfig())


class TestDryRunPlan:
    def test_returns_plan_without_side_effects(self) -> None:
        p = _svc().plan("What does a data analyst do?")
        assert isinstance(p, PipelinePlan)
        assert p.steps[0].startswith("Validate")
        assert p.steps[-1].startswith("Synthesise")

    def test_salary_query_routes_to_compensation_lane(self) -> None:
        p = _svc().plan("What does a nurse earn in the UK?")
        assert p.retrieval_lane == "compensation"
        assert p.detected_country == "UK"

    def test_preparation_expects_all_tools_when_inputs_present(self) -> None:
        p = _svc().plan(
            "Help me prepare a study plan for this role",
            job_description="Data analyst: SQL, Python, dashboards",
            candidate_background="2 years in support",
            days_until_interview=10, hours_per_week=8)
        assert "candidate_gap_analyzer" in p.tools_expected_to_run
        assert not p.tools_skipped_no_input

    def test_preparation_skips_tools_without_inputs(self) -> None:
        p = _svc().plan("Help me prepare a study plan for this role")
        # No JD/background/timeframe → tools are planned but skipped, and surfaced.
        assert p.tools_skipped_no_input
        assert any("Provide more inputs" in n for n in p.notes)

    def test_plan_is_pure_no_synthesis_responder_needed(self) -> None:
        # A service with no synthesis responder must still plan (proves no LLM).
        svc = CareerIntelligenceService(config=None)
        p = svc.plan("How do I transition into cybersecurity?")
        assert p.intent and p.steps
