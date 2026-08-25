"""Phase 6 tests: domain tool calling.

Deterministic tools are tested directly; LLM-backed tools use injected fake
producers (no network, no paid API calls). Tool-call parsing uses a real
LangChain AIMessage.
"""

from types import SimpleNamespace

import pytest

from src.copilot import constants
from src.copilot.tools import (
    ToolInvoker,
    build_langchain_tools,
    build_tool_registry,
    parse_tool_calls,
)
from src.copilot.tools.gap_analyzer import analyze_gaps
from src.copilot.tools.prep_planner import build_plan
from src.copilot.tools.registry import run_model_with_tools
from src.copilot.tools.schemas import (
    GapAnalyzerArgs,
    InterviewQuestionSet,
    PrepPlanArgs,
    PriorityGap,
    QuestionCategory,
    RoleRequirements,
)


# --- Fake producers (stand in for the LLM) -----------------------------------


def _fake_job_producer(messages):
    return RoleRequirements(
        role_title="Data Engineer",
        seniority="Senior",
        required_skills=["Python", "SQL"],
        technologies=["AWS"],
        likely_interview_themes=["data pipelines"],
        interpretation_notes=["Team leadership may be expected (not explicit)."],
    )


def _fake_question_producer(messages):
    return InterviewQuestionSet(
        role="Data Engineer",
        categories=[
            QuestionCategory(name="technical", questions=["Explain a data pipeline you built."]),
            QuestionCategory(name="behavioural", questions=["Tell me about a conflict."]),
        ],
    )


def _registry():
    return build_tool_registry(
        config=None,
        job_producer=_fake_job_producer,
        question_producer=_fake_question_producer,
    )


# --- Deterministic gap analysis ----------------------------------------------


class TestGapAnalyzer:
    def test_match_calculation_is_deterministic(self) -> None:
        reqs = RoleRequirements(
            required_skills=["Python", "team leadership and mentoring"],
            technologies=["AWS"],
        )
        args = GapAnalyzerArgs(
            candidate_background="Python developer who led a team.",
            role_requirements=reqs,
        )
        result = analyze_gaps(args)
        assert result.stats.total_requirements == 3
        assert result.stats.matched == 1  # Python
        assert result.stats.partial == 1  # led a team -> partial leadership
        assert result.stats.missing == 1  # AWS
        assert result.stats.match_percentage == pytest.approx(33.3, abs=0.1)
        assert result.stats.weighted_match_percentage == pytest.approx(50.0, abs=0.1)
        assert "Python" in result.strengths

    def test_priority_gaps_ordered_by_severity(self) -> None:
        reqs = RoleRequirements(
            required_skills=["Kubernetes"],  # high, missing
            preferred_skills=["Terraform"],  # low, missing
        )
        result = analyze_gaps(
            GapAnalyzerArgs(candidate_background="Generalist.", role_requirements=reqs)
        )
        severities = [g.severity for g in result.priority_gaps]
        assert severities == ["high", "low"]

    def test_empty_requirements_no_division_error(self) -> None:
        result = analyze_gaps(
            GapAnalyzerArgs(candidate_background="Anything", role_requirements=RoleRequirements())
        )
        assert result.stats.total_requirements == 0
        assert result.stats.match_percentage == 0.0


# --- Deterministic preparation plan ------------------------------------------


class TestPrepPlanner:
    def test_arithmetic_is_deterministic(self) -> None:
        gaps = [
            PriorityGap(requirement="AWS", severity="high"),
            PriorityGap(requirement="Docker", severity="low"),
        ]
        plan = build_plan(
            PrepPlanArgs(priority_gaps=gaps, days_until_interview=14, hours_per_week=10)
        )
        assert plan.total_available_hours == pytest.approx(20.0)
        alloc = {a.requirement: a for a in plan.allocations}
        assert alloc["AWS"].allocated_hours == pytest.approx(15.0)   # 3/4 of 20
        assert alloc["Docker"].allocated_hours == pytest.approx(5.0)  # 1/4 of 20
        assert alloc["AWS"].share_percentage == pytest.approx(75.0)
        # Allocations sum to the total (within rounding).
        assert sum(a.allocated_hours for a in plan.allocations) == pytest.approx(20.0)

    def test_weekly_structure(self) -> None:
        gaps = [PriorityGap(requirement="AWS", severity="high")]
        plan = build_plan(
            PrepPlanArgs(priority_gaps=gaps, days_until_interview=14, hours_per_week=8)
        )
        assert len(plan.weekly_structure) == 2
        assert plan.weekly_structure[0].hours == pytest.approx(8.0)
        assert "AWS" in plan.weekly_structure[0].focus

    def test_partial_final_week(self) -> None:
        plan = build_plan(
            PrepPlanArgs(
                priority_gaps=[PriorityGap(requirement="X", severity="medium")],
                days_until_interview=10,
                hours_per_week=7,
            )
        )
        # 10 days -> 2 weeks; final week is 3 days -> 3 hours.
        assert plan.weekly_structure[-1].hours == pytest.approx(3.0)


# --- Invoker: job + question tools -------------------------------------------


class TestInvokerLLMTools:
    def test_job_analysis_tool_call(self) -> None:
        invoker = ToolInvoker(_registry())
        jd = "We need a Senior Data Engineer with Python and SQL and AWS."
        result = invoker.invoke(constants.TOOL_JOB_ANALYZER, {"job_description": jd})
        assert result.ok
        assert isinstance(result.result, RoleRequirements)
        assert result.execution.status == "ok"
        assert result.execution.duration_seconds >= 0.0
        # Safe summary must NOT contain the raw JD text.
        assert jd not in result.execution.safe_argument_summary
        assert "chars" in result.execution.safe_argument_summary

    def test_question_generation_tool_call(self) -> None:
        invoker = ToolInvoker(_registry())
        result = invoker.invoke(
            constants.TOOL_QUESTION_GENERATOR,
            {"role": "Data Engineer", "requirements": ["Python"]},
        )
        assert result.ok
        assert isinstance(result.result, InterviewQuestionSet)
        assert "questions across" in result.execution.safe_result_summary


# --- Invoker: sequential pipeline --------------------------------------------


def test_sequential_tools_pipeline() -> None:
    invoker = ToolInvoker(_registry())
    jd = "Senior Data Engineer: Python, SQL, AWS. Lead a small team."
    job = invoker.invoke(constants.TOOL_JOB_ANALYZER, {"job_description": jd})
    assert job.ok

    gap = invoker.invoke(
        constants.TOOL_GAP_ANALYZER,
        {
            "candidate_background": "Python and SQL engineer.",
            "role_requirements": job.result.model_dump(),
        },
    )
    assert gap.ok and gap.result.stats.total_requirements > 0

    prep = invoker.invoke(
        constants.TOOL_PREP_PLANNER,
        {
            "priority_gaps": [g.model_dump() for g in gap.result.priority_gaps] or
            [{"requirement": "AWS", "severity": "medium"}],
            "days_until_interview": 7,
            "hours_per_week": 5,
        },
    )
    assert prep.ok and prep.result.total_available_hours == pytest.approx(5.0)


# --- Invoker: error handling -------------------------------------------------


class TestInvokerErrors:
    def test_malformed_arguments(self) -> None:
        invoker = ToolInvoker(_registry())
        # Missing required role_requirements.
        result = invoker.invoke(constants.TOOL_GAP_ANALYZER, {"candidate_background": "x"})
        assert result.execution.status == "invalid_args"
        assert result.result is None

    def test_empty_job_description_rejected(self) -> None:
        invoker = ToolInvoker(_registry())
        result = invoker.invoke(constants.TOOL_JOB_ANALYZER, {"job_description": ""})
        assert result.execution.status == "invalid_args"

    def test_tool_exception_is_captured(self) -> None:
        def boom(messages):
            raise RuntimeError("secret detail should not leak")

        registry = build_tool_registry(config=None, job_producer=boom)
        invoker = ToolInvoker(registry)
        result = invoker.invoke(
            constants.TOOL_JOB_ANALYZER, {"job_description": "valid JD text"}
        )
        assert result.execution.status == "error"
        assert "secret detail" not in (result.execution.error or "")
        assert result.execution.error == "RuntimeError during tool execution."

    def test_unsupported_tool(self) -> None:
        invoker = ToolInvoker(_registry())
        result = invoker.invoke("os_system", {"cmd": "rm -rf /"})
        assert result.execution.status == "unsupported"
        assert result.result is None

    def test_no_arbitrary_tool_execution(self) -> None:
        invoker = ToolInvoker(_registry())
        for evil in ("eval", "exec", "subprocess.run", "open", "__import__"):
            assert invoker.invoke(evil, {}).execution.status == "unsupported"


# --- LangChain tool-calling glue ---------------------------------------------


class TestLangChainGlue:
    def test_build_langchain_tools_only_registered(self) -> None:
        tools = build_langchain_tools(_registry())
        names = {t.name for t in tools}
        assert names == set(constants.REGISTERED_TOOLS)
        assert all(t.args_schema is not None for t in tools)

    def test_parse_tool_calls_from_ai_message(self) -> None:
        pytest.importorskip("langchain_core")
        from langchain_core.messages import AIMessage

        msg = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": constants.TOOL_PREP_PLANNER,
                    "args": {"a": 1},
                    "id": "call_1",
                    "type": "tool_call",
                }
            ],
        )
        calls = parse_tool_calls(msg)
        assert len(calls) == 1
        assert calls[0].name == constants.TOOL_PREP_PLANNER
        assert calls[0].id == "call_1"

    def test_parse_tool_calls_from_dict(self) -> None:
        msg = {"tool_calls": [{"name": "x", "args": {}, "id": "1"}]}
        assert parse_tool_calls(msg)[0].name == "x"

    def test_run_model_dispatches_tool_calls(self) -> None:
        invoker = ToolInvoker(_registry())
        gaps = [{"requirement": "AWS", "severity": "high"}]
        fake_ai = SimpleNamespace(
            content="",
            tool_calls=[
                {
                    "name": constants.TOOL_PREP_PLANNER,
                    "args": {
                        "priority_gaps": gaps,
                        "days_until_interview": 7,
                        "hours_per_week": 4,
                    },
                    "id": "1",
                }
            ],
        )
        fake_model = SimpleNamespace(invoke=lambda messages: fake_ai)
        ai, results = run_model_with_tools(fake_model, [], invoker)
        assert len(results) == 1 and results[0].ok
        assert results[0].result.total_available_hours == pytest.approx(4.0)

    def test_no_tool_needed_case(self) -> None:
        invoker = ToolInvoker(_registry())
        fake_ai = SimpleNamespace(content="Just a chat answer.", tool_calls=[])
        fake_model = SimpleNamespace(invoke=lambda messages: fake_ai)
        ai, results = run_model_with_tools(fake_model, [], invoker)
        assert results == []
        assert ai.content == "Just a chat answer."
