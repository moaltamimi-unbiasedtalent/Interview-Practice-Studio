"""Explicit Pydantic argument and result schemas for the domain tools.

Every tool has a strict argument schema (``extra="forbid"``) used both for
validation and as the LangChain tool schema, and a validated structured result.
Keeping these here (separate from core ``models``) makes the tool contract easy
to read for a project review.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.copilot import constants

__all__ = [
    "RoleRequirements",
    "PriorityGap",
    "MatchStats",
    "GapAnalysisResult",
    "GapAllocation",
    "WeekPlan",
    "PreparationPlan",
    "QuestionCategory",
    "InterviewQuestionSet",
    "JobAnalyzerArgs",
    "GapAnalyzerArgs",
    "PrepPlanArgs",
    "QuestionGeneratorArgs",
]


class _Args(BaseModel):
    """Strict base for tool arguments (reject unknown keys, trim strings)."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class _Result(BaseModel):
    """Lenient base for tool results (validated, but tolerant of extra keys)."""

    model_config = ConfigDict(str_strip_whitespace=True)


# --- Shared structured types -------------------------------------------------


class RoleRequirements(_Result):
    """Structured requirements inferred from a job description.

    The named lists hold requirements **explicitly present** in the text;
    ``interpretation_notes`` holds reasonable interpretation that is *not*
    explicitly stated, kept separate so the two are never conflated.
    """

    role_title: str | None = None
    seniority: str | None = None
    key_responsibilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    leadership_expectations: list[str] = Field(default_factory=list)
    stakeholder_expectations: list[str] = Field(default_factory=list)
    likely_interview_themes: list[str] = Field(default_factory=list)
    interpretation_notes: list[str] = Field(
        default_factory=list,
        description="Reasonable interpretation NOT explicitly stated in the JD.",
    )

    def scored_requirements(self) -> list[tuple[str, str, str]]:
        """Return ``(requirement, category, severity)`` tuples for gap analysis.

        Required skills and responsibilities are high severity, technologies
        medium, preferred skills low.
        """
        items: list[tuple[str, str, str]] = []
        for skill in self.required_skills:
            items.append((skill, "required_skill", "high"))
        for resp in self.key_responsibilities:
            items.append((resp, "responsibility", "high"))
        for tech in self.technologies:
            items.append((tech, "technology", "medium"))
        for skill in self.preferred_skills:
            items.append((skill, "preferred_skill", "low"))
        return items


class PriorityGap(_Result):
    """One requirement the candidate does not fully meet."""

    requirement: str
    category: str = "requirement"
    severity: str = Field(default="medium", description="high | medium | low")
    reason: str = ""


class MatchStats(_Result):
    """Deterministic match statistics (computed in Python, never by the LLM)."""

    total_requirements: int = 0
    matched: int = 0
    partial: int = 0
    missing: int = 0
    match_percentage: float = 0.0
    weighted_match_percentage: float = 0.0


class GapAnalysisResult(_Result):
    matched: list[str] = Field(default_factory=list)
    partially_matched: list[str] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    priority_gaps: list[PriorityGap] = Field(default_factory=list)
    stats: MatchStats = Field(default_factory=MatchStats)


class GapAllocation(_Result):
    requirement: str
    severity: str = "medium"
    allocated_hours: float = 0.0
    share_percentage: float = 0.0
    actions: list[str] = Field(default_factory=list)


class WeekPlan(_Result):
    week: int
    hours: float = 0.0
    focus: list[str] = Field(default_factory=list)


class PreparationPlan(_Result):
    days_until_interview: int = 0
    hours_per_week: float = 0.0
    total_available_hours: float = 0.0
    allocations: list[GapAllocation] = Field(default_factory=list)
    weekly_structure: list[WeekPlan] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class QuestionCategory(_Result):
    name: str
    questions: list[str] = Field(default_factory=list)


class InterviewQuestionSet(_Result):
    role: str = ""
    categories: list[QuestionCategory] = Field(default_factory=list)


# --- Tool argument schemas ---------------------------------------------------


class JobAnalyzerArgs(_Args):
    """Arguments for the Job Description Analyzer."""

    job_description: str = Field(
        min_length=1,
        max_length=constants.MAX_JOB_DESCRIPTION_CHARS,
        description="The full pasted job description text to analyse.",
    )
    focus: str | None = Field(
        default=None,
        description="Optional aspect to emphasise, e.g. 'leadership' or 'technical'.",
    )


class GapAnalyzerArgs(_Args):
    """Arguments for the Candidate Gap Analyzer."""

    candidate_background: str = Field(
        min_length=1,
        max_length=constants.MAX_CANDIDATE_BACKGROUND_CHARS,
        description="The candidate's background/CV summary text.",
    )
    role_requirements: RoleRequirements = Field(
        description="Structured role requirements (e.g. from the Job Description Analyzer)."
    )


class PrepPlanArgs(_Args):
    """Arguments for the Preparation Plan Calculator."""

    priority_gaps: list[PriorityGap] = Field(
        min_length=1, description="Gaps to prepare for (from the Gap Analyzer)."
    )
    days_until_interview: int = Field(
        ge=1, le=365, description="Whole days remaining before the interview."
    )
    hours_per_week: float = Field(
        gt=0, le=168, description="Hours the candidate can study per week."
    )


class QuestionGeneratorArgs(_Args):
    """Arguments for the Interview Question Generator."""

    role: str = Field(min_length=1, description="Target role title.")
    requirements: list[str] = Field(
        default_factory=list, description="Key role requirements to probe."
    )
    findings: list[str] = Field(
        default_factory=list, description="Career-intelligence findings for context."
    )
    evidence: list[str] = Field(
        default_factory=list, description="Retrieved evidence snippets for grounding."
    )
    focus: list[str] = Field(
        default_factory=list,
        description=f"Desired categories, subset of {list(constants.QUESTION_CATEGORIES)}.",
    )
    per_category: int = Field(
        default=3, ge=1, le=10, description="Questions to generate per category."
    )
