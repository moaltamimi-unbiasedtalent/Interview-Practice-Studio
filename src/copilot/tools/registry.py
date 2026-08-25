"""Tool registry, safe invoker and LangChain tool-calling glue.

The registry is the ONLY set of functions the model may invoke. Invocation goes
through :class:`ToolInvoker`, which validates arguments against the tool's Pydantic
schema, times the call, captures a safe :class:`ToolExecution` record (no raw
candidate/JD text) and never lets the model reach arbitrary code: an unknown tool
name is rejected as ``unsupported``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.models import ToolExecution
from src.copilot.tools import gap_analyzer, job_analyzer, prep_planner, question_generator
from src.copilot.tools.errors import ToolError
from src.copilot.tools.schemas import (
    GapAnalyzerArgs,
    JobAnalyzerArgs,
    PrepPlanArgs,
    QuestionGeneratorArgs,
)
from src.copilot.tools.structured import StructuredProducer

__all__ = [
    "ToolSpec",
    "ToolResult",
    "ToolCallRequest",
    "ToolInvoker",
    "build_tool_registry",
    "build_langchain_tools",
    "parse_tool_calls",
    "run_model_with_tools",
]


@dataclass
class ToolSpec:
    """A single registered tool the model may call."""

    name: str
    description: str
    args_schema: type[BaseModel]
    func: Callable[[BaseModel], BaseModel]
    summarize_args: Callable[[BaseModel], str]
    summarize_result: Callable[[Any], str]


@dataclass
class ToolResult:
    """The outcome of one tool invocation: a safe record + the typed result."""

    execution: ToolExecution
    result: BaseModel | None = None

    @property
    def ok(self) -> bool:
        return self.execution.status == "ok"


@dataclass
class ToolCallRequest:
    """A parsed tool-call request from a model message."""

    name: str
    args: dict = field(default_factory=dict)
    id: str | None = None


# --- Safe summaries (never include raw JD / candidate text) ------------------


def _summ_job_args(a: JobAnalyzerArgs) -> str:
    focus = f", focus={a.focus}" if a.focus else ""
    return f"job_description ({len(a.job_description)} chars){focus}"


def _summ_job_result(r: Any) -> str:
    return (
        f"role={r.role_title or 'n/a'}; {len(r.required_skills)} required skills, "
        f"{len(r.technologies)} tools, {len(r.likely_interview_themes)} themes"
    )


def _summ_gap_args(a: GapAnalyzerArgs) -> str:
    n = len(a.role_requirements.scored_requirements())
    return f"candidate_background ({len(a.candidate_background)} chars); {n} requirements"


def _summ_gap_result(r: Any) -> str:
    s = r.stats
    return (
        f"{s.matched} matched / {s.partial} partial / {s.missing} missing; "
        f"match {s.match_percentage}%"
    )


def _summ_prep_args(a: PrepPlanArgs) -> str:
    return (
        f"{len(a.priority_gaps)} gaps; {a.days_until_interview} days; "
        f"{a.hours_per_week} h/week"
    )


def _summ_prep_result(r: Any) -> str:
    return (
        f"{r.total_available_hours}h across {len(r.allocations)} gaps, "
        f"{len(r.weekly_structure)} weeks"
    )


def _summ_q_args(a: QuestionGeneratorArgs) -> str:
    return f"role={a.role}; {len(a.requirements)} reqs; focus={a.focus or 'default'}"


def _summ_q_result(r: Any) -> str:
    total = sum(len(c.questions) for c in r.categories)
    return f"{total} questions across {len(r.categories)} categories"


def build_tool_registry(
    config: CopilotConfig | None = None,
    *,
    job_producer: StructuredProducer | None = None,
    question_producer: StructuredProducer | None = None,
) -> dict[str, ToolSpec]:
    """Build the registry of callable tools.

    The LLM-backed tools (job analyzer, question generator) use the injected
    producer if given, otherwise one built from ``config`` at call time. The
    deterministic tools need neither.
    """
    return {
        constants.TOOL_JOB_ANALYZER: ToolSpec(
            name=constants.TOOL_JOB_ANALYZER,
            description=(
                "Analyse a pasted job description into structured role requirements "
                "(responsibilities, required/preferred skills, technologies, "
                "leadership & stakeholder expectations, likely interview themes). "
                "Use when the user provides a job description. Do NOT use for "
                "general career questions or when no JD text is supplied. "
                "Parameter job_description: the full JD text; focus: optional aspect "
                "to emphasise."
            ),
            args_schema=JobAnalyzerArgs,
            func=lambda a: job_analyzer.analyze_job(
                a, producer=job_producer, config=config
            ),
            summarize_args=_summ_job_args,
            summarize_result=_summ_job_result,
        ),
        constants.TOOL_GAP_ANALYZER: ToolSpec(
            name=constants.TOOL_GAP_ANALYZER,
            description=(
                "Compare a candidate background against structured role requirements "
                "and return matched / partial / missing requirements, strengths, "
                "priority gaps and deterministic match statistics. Use when you have "
                "both a candidate background and role requirements. Not a hiring "
                "decision. Parameters: candidate_background text; role_requirements "
                "(from the job description analyzer)."
            ),
            args_schema=GapAnalyzerArgs,
            func=lambda a: gap_analyzer.analyze_gaps(a),
            summarize_args=_summ_gap_args,
            summarize_result=_summ_gap_result,
        ),
        constants.TOOL_PREP_PLANNER: ToolSpec(
            name=constants.TOOL_PREP_PLANNER,
            description=(
                "Compute a deterministic, time-boxed preparation plan from priority "
                "gaps, days until the interview and available hours per week. Use "
                "after a gap analysis when the user wants a study plan. Parameters: "
                "priority_gaps; days_until_interview; hours_per_week."
            ),
            args_schema=PrepPlanArgs,
            func=lambda a: prep_planner.build_plan(a),
            summarize_args=_summ_prep_args,
            summarize_result=_summ_prep_result,
        ),
        constants.TOOL_QUESTION_GENERATOR: ToolSpec(
            name=constants.TOOL_QUESTION_GENERATOR,
            description=(
                "Generate likely interview questions across categories (behavioural, "
                "situational, competency, technical, leadership, stakeholder, "
                "executive, culture/values), grounded in the role, requirements, "
                "findings and evidence. Use to prepare questions; this does NOT run "
                "an interview simulation. Parameters: role; requirements; findings; "
                "evidence; focus; per_category."
            ),
            args_schema=QuestionGeneratorArgs,
            func=lambda a: question_generator.generate_questions(
                a, producer=question_producer, config=config
            ),
            summarize_args=_summ_q_args,
            summarize_result=_summ_q_result,
        ),
    }


class ToolInvoker:
    """Validate, execute and record tool calls against a fixed registry."""

    def __init__(self, registry: dict[str, ToolSpec]) -> None:
        self.registry = registry

    def invoke(self, name: str, raw_args: dict | None) -> ToolResult:
        raw_args = raw_args or {}
        spec = self.registry.get(name)
        if spec is None:
            return ToolResult(
                execution=ToolExecution(
                    tool_name=name,
                    status="unsupported",
                    error=f"Unknown tool {name!r}; not in the registered tool set.",
                )
            )

        # 1) validate arguments against the tool's schema.
        try:
            args = spec.args_schema.model_validate(raw_args)
        except ValidationError as exc:
            return ToolResult(
                execution=ToolExecution(
                    tool_name=name,
                    status="invalid_args",
                    error=f"Invalid arguments ({exc.error_count()} error(s)).",
                )
            )

        # 2) execute, timing the call and keeping errors safe.
        start = time.perf_counter()
        try:
            result = spec.func(args)
        except ToolError as exc:
            duration = time.perf_counter() - start
            return ToolResult(
                execution=ToolExecution(
                    tool_name=name,
                    status="error",
                    duration_seconds=round(duration, 4),
                    safe_argument_summary=spec.summarize_args(args),
                    error=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001 - keep the message safe/generic
            duration = time.perf_counter() - start
            return ToolResult(
                execution=ToolExecution(
                    tool_name=name,
                    status="error",
                    duration_seconds=round(duration, 4),
                    safe_argument_summary=spec.summarize_args(args),
                    error=f"{type(exc).__name__} during tool execution.",
                )
            )
        duration = time.perf_counter() - start

        return ToolResult(
            execution=ToolExecution(
                tool_name=name,
                status="ok",
                duration_seconds=round(duration, 4),
                safe_argument_summary=spec.summarize_args(args),
                safe_result_summary=spec.summarize_result(result),
            ),
            result=result,
        )


# --- LangChain tool-calling glue --------------------------------------------


def build_langchain_tools(
    registry: dict[str, ToolSpec], invoker: ToolInvoker | None = None
) -> list:
    """Build LangChain ``StructuredTool``s to advertise to the model.

    Executing through the returned tools routes back through :class:`ToolInvoker`,
    so the same validation and safe records apply. Primarily these are bound to
    the model so it can *choose* tools; we then dispatch parsed calls ourselves.
    """
    from langchain_core.tools import StructuredTool

    invoker = invoker or ToolInvoker(registry)
    tools = []
    for spec in registry.values():

        def _runner(_spec_name: str = spec.name, **kwargs):
            result = invoker.invoke(_spec_name, kwargs)
            if result.result is not None:
                return result.result.model_dump()
            return {"status": result.execution.status, "error": result.execution.error}

        tools.append(
            StructuredTool.from_function(
                func=_runner,
                name=spec.name,
                description=spec.description,
                args_schema=spec.args_schema,
            )
        )
    return tools


def parse_tool_calls(message: Any) -> list[ToolCallRequest]:
    """Parse tool calls from a LangChain AIMessage (or a dict-like message)."""
    raw = getattr(message, "tool_calls", None)
    if raw is None and isinstance(message, dict):
        raw = message.get("tool_calls")
    requests: list[ToolCallRequest] = []
    for call in raw or []:
        name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
        args = (
            call.get("args") if isinstance(call, dict) else getattr(call, "args", None)
        ) or {}
        call_id = call.get("id") if isinstance(call, dict) else getattr(call, "id", None)
        if name:
            requests.append(ToolCallRequest(name=name, args=dict(args), id=call_id))
    return requests


def run_model_with_tools(
    chat_model: Any, messages: list, invoker: ToolInvoker
) -> tuple[Any, list[ToolResult]]:
    """Invoke a (tool-bound) chat model and dispatch any tool calls it requests.

    Controlled, single-pass tool calling — not an autonomous loop. Returns the AI
    message and the list of :class:`ToolResult`s (empty when no tool was needed).
    """
    ai_message = chat_model.invoke(messages)
    results = [
        invoker.invoke(call.name, call.args)
        for call in parse_tool_calls(ai_message)
    ]
    return ai_message, results
