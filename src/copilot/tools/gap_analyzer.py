"""Candidate Gap Analyzer — deterministic, no LLM.

Compares a candidate background against structured role requirements and computes
match statistics **in Python** from explicit token-coverage criteria. There is no
LLM-invented "match score": every number is derived and reproducible. This is
development coaching, not an automated hiring decision.
"""

from __future__ import annotations

from src.copilot import constants
from src.copilot.tools.schemas import (
    GapAnalysisResult,
    GapAnalyzerArgs,
    MatchStats,
    PriorityGap,
)
from src.copilot.tools.text_match import coverage, significant_tokens

__all__ = ["analyze_gaps", "MATCH_THRESHOLD", "PARTIAL_THRESHOLD"]

# Coverage at/above this counts as a full match; above 0 but below it is partial.
MATCH_THRESHOLD = 1.0
PARTIAL_THRESHOLD = 0.0


def _severity_rank(severity: str) -> int:
    order = constants.SEVERITY_ORDER
    return order.index(severity) if severity in order else len(order)


def analyze_gaps(args: GapAnalyzerArgs) -> GapAnalysisResult:
    """Deterministically classify each requirement as matched/partial/missing."""
    candidate_tokens = significant_tokens(args.candidate_background)
    requirements = args.role_requirements.scored_requirements()

    matched: list[str] = []
    partial: list[str] = []
    missing: list[str] = []
    strengths: list[str] = []
    priority_gaps: list[PriorityGap] = []

    for requirement, category, severity in requirements:
        cov = coverage(requirement, candidate_tokens)
        if cov >= MATCH_THRESHOLD:
            matched.append(requirement)
            if category in ("required_skill", "technology"):
                strengths.append(requirement)
        elif cov > PARTIAL_THRESHOLD:
            partial.append(requirement)
            priority_gaps.append(
                PriorityGap(
                    requirement=requirement,
                    category=category,
                    severity=severity,
                    reason=f"Partially evidenced (coverage {cov:.0%}).",
                )
            )
        else:
            missing.append(requirement)
            priority_gaps.append(
                PriorityGap(
                    requirement=requirement,
                    category=category,
                    severity=severity,
                    reason="Not evidenced in the candidate background.",
                )
            )

    # Missing before partial within a severity band; higher severity first.
    priority_gaps.sort(
        key=lambda gap: (_severity_rank(gap.severity), gap.requirement in partial)
    )

    total = len(requirements)
    n_matched, n_partial, n_missing = len(matched), len(partial), len(missing)
    if total:
        match_pct = round(100.0 * n_matched / total, 1)
        weighted_pct = round(100.0 * (n_matched + 0.5 * n_partial) / total, 1)
    else:
        match_pct = weighted_pct = 0.0

    stats = MatchStats(
        total_requirements=total,
        matched=n_matched,
        partial=n_partial,
        missing=n_missing,
        match_percentage=match_pct,
        weighted_match_percentage=weighted_pct,
    )
    return GapAnalysisResult(
        matched=matched,
        partially_matched=partial,
        missing=missing,
        strengths=strengths,
        priority_gaps=priority_gaps,
        stats=stats,
    )
