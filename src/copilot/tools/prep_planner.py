"""Preparation Plan Calculator — deterministic Python arithmetic.

All time allocation and arithmetic is computed here in Python: total available
hours, per-gap hours weighted by severity, and a week-by-week structure. The
model never performs hidden arithmetic; it may only describe learning actions
(here provided as deterministic templates).
"""

from __future__ import annotations

import math

from src.copilot import constants
from src.copilot.tools.schemas import (
    GapAllocation,
    PrepPlanArgs,
    PreparationPlan,
    WeekPlan,
)

__all__ = ["build_plan", "recommended_actions"]


def recommended_actions(requirement: str, severity: str) -> list[str]:
    """Deterministic learning-action templates for a gap (no arithmetic, no LLM)."""
    actions = [
        f"Review the fundamentals of {requirement}.",
        f"Practise {requirement} with targeted exercises or examples.",
        f"Prepare a concrete story that demonstrates {requirement}.",
    ]
    if severity == "high":
        actions.append(f"Do a timed mock question focused on {requirement}.")
    return actions


def _weight(severity: str) -> float:
    return constants.SEVERITY_WEIGHTS.get(severity, constants.SEVERITY_WEIGHTS["medium"])


def build_plan(args: PrepPlanArgs) -> PreparationPlan:
    """Compute a prioritised, time-boxed preparation plan deterministically."""
    days = args.days_until_interview
    hours_per_week = args.hours_per_week
    total_hours = round(hours_per_week * (days / 7.0), 2)

    gaps = list(args.priority_gaps)
    weights = [_weight(gap.severity) for gap in gaps]
    total_weight = sum(weights)

    allocations: list[GapAllocation] = []
    for gap, weight in zip(gaps, weights):
        share = (weight / total_weight) if total_weight else 0.0
        allocations.append(
            GapAllocation(
                requirement=gap.requirement,
                severity=gap.severity,
                allocated_hours=round(total_hours * share, 2),
                share_percentage=round(100.0 * share, 1),
                actions=recommended_actions(gap.requirement, gap.severity),
            )
        )

    # Highest-weight gaps first so early weeks tackle the most severe.
    ordered = sorted(
        range(len(gaps)), key=lambda i: weights[i], reverse=True
    )
    weeks = max(1, math.ceil(days / 7.0))
    focus_by_week: list[list[str]] = [[] for _ in range(weeks)]
    for position, gap_index in enumerate(ordered):
        focus_by_week[position % weeks].append(gaps[gap_index].requirement)

    weekly_structure: list[WeekPlan] = []
    remaining_days = days
    for week in range(1, weeks + 1):
        week_days = min(7, remaining_days)
        remaining_days -= week_days
        weekly_structure.append(
            WeekPlan(
                week=week,
                hours=round(hours_per_week * (week_days / 7.0), 2),
                focus=focus_by_week[week - 1],
            )
        )

    notes = [
        "Hours are computed deterministically: total = hours_per_week × days ÷ 7, "
        "split across gaps by severity weight (high 3 / medium 2 / low 1).",
    ]
    if total_hours < 5:
        notes.append("Limited total time — focus on the highest-severity gaps first.")

    return PreparationPlan(
        days_until_interview=days,
        hours_per_week=hours_per_week,
        total_available_hours=total_hours,
        allocations=allocations,
        weekly_structure=weekly_structure,
        notes=notes,
    )
