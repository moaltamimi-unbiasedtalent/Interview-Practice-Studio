"""Deterministic intent routing for the orchestration layer.

Maps a classified intent to whether RAG is required and which tools are relevant.
This is a fixed table, not an autonomous planner: the model never decides the
route. Whether a *relevant* tool actually runs also depends on the inputs the
caller supplied (a JD, a candidate background, a timeframe).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.copilot import constants

__all__ = ["Route", "route_for_intent"]


@dataclass(frozen=True)
class Route:
    """The plan for an intent: RAG requirement and candidate tools (in order)."""

    rag_required: bool
    tools: tuple[str, ...] = field(default_factory=tuple)


_ROUTES: dict[str, Route] = {
    "factual_career": Route(rag_required=True),
    "role_research": Route(rag_required=True),
    "skill_research": Route(rag_required=True),
    "job_description_analysis": Route(
        rag_required=False, tools=(constants.TOOL_JOB_ANALYZER,)
    ),
    "candidate_comparison": Route(
        rag_required=True,
        tools=(constants.TOOL_JOB_ANALYZER, constants.TOOL_GAP_ANALYZER),
    ),
    "preparation_planning": Route(
        rag_required=True,
        tools=(
            constants.TOOL_JOB_ANALYZER,
            constants.TOOL_GAP_ANALYZER,
            constants.TOOL_PREP_PLANNER,
        ),
    ),
    "interview_preparation": Route(
        rag_required=True, tools=(constants.TOOL_QUESTION_GENERATOR,)
    ),
    "smalltalk": Route(rag_required=False),
    "other": Route(rag_required=True),
}


def route_for_intent(intent: str) -> Route:
    """Return the route for an intent (defaults to RAG-only for unknown intents)."""
    return _ROUTES.get(intent, Route(rag_required=True))
