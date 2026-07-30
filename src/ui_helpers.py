"""Pure UI helpers for the Streamlit app.

Keeps the mapping between human-readable labels and domain identifiers, plus
serialization and formatting helpers, out of ``app.py`` so they can be
unit-tested without a running Streamlit server. Nothing here calls Streamlit or
the network; importing this module has no side effects.
"""

from __future__ import annotations

from src import constants
from src import prompt_registry as registry
from src.models import (
    AnswerEvaluation,
    FinalInterviewReport,
    InterviewConfiguration,
)

__all__ = [
    "CAREER_LEVELS",
    "INTERVIEW_TYPES",
    "PERSONAS",
    "DIFFICULTIES",
    "RESPONSE_DETAILS",
    "MODELS",
    "RUBRIC_CRITERIA",
    "labels",
    "id_for_label",
    "label_for_id",
    "technique_options",
    "difficulty_default_index",
    "report_to_markdown",
    "report_to_json",
    "format_usd",
]

# --- Label ↔ domain-id catalogues -------------------------------------------
# Each entry is (human label shown in the UI, domain id stored in the model).
# The ids are validated against src.constants by the domain models.

CAREER_LEVELS: list[tuple[str, str]] = [
    ("Internship or apprenticeship", "internship"),
    ("Entry level", "entry"),
    ("Professional", "mid"),
    ("Senior professional", "senior"),
    ("Manager", "manager"),
    ("Director", "director"),
    ("Executive", "executive"),
]

INTERVIEW_TYPES: list[tuple[str, str]] = [
    ("Recruiter screening", "screening"),
    ("Behavioural", "behavioural"),
    ("Technical or functional", "technical"),
    ("Case or problem-solving", "case_study"),
    ("Leadership", "leadership"),
    ("Culture and values", "culture_values"),
    ("Stakeholder or client", "stakeholder"),
    ("Panel", "panel"),
    ("Executive or board", "executive_board"),
]

PERSONAS: list[tuple[str, str]] = [
    ("Friendly recruiter", "supportive"),
    ("Neutral hiring manager", "neutral"),
    ("Challenging functional expert", "challenging"),
    ("Sceptical executive", "sceptical_executive"),
    ("Fast-paced panel", "fast_paced_panel"),
]

DIFFICULTIES: list[tuple[str, str]] = [
    ("Easy", "easy"),
    ("Medium", "moderate"),
    ("Hard", "hard"),
]

RESPONSE_DETAILS: list[tuple[str, str]] = [
    ("Concise", "brief"),
    ("Balanced", "standard"),
    ("Detailed", "detailed"),
]

# Model ids in a sensible display order (default first).
MODELS: list[str] = [
    constants.DEFAULT_MODEL,
    constants.LOW_COST_MODEL,
    constants.HIGH_CAPABILITY_MODEL,
]

# The seven rubric criteria (AnswerEvaluation field name → friendly label).
RUBRIC_CRITERIA: list[tuple[str, str]] = [
    ("relevance", "Relevance"),
    ("structure", "Structure"),
    ("evidence", "Evidence"),
    ("role_knowledge", "Role knowledge"),
    ("problem_solving", "Problem solving"),
    ("communication", "Communication"),
    ("credibility", "Credibility"),
]


# --- Small pure helpers ------------------------------------------------------


def labels(pairs: list[tuple[str, str]]) -> list[str]:
    """Return just the display labels from a catalogue."""
    return [label for label, _ in pairs]


def id_for_label(pairs: list[tuple[str, str]], label: str) -> str:
    """Map a display label back to its domain id."""
    return dict(pairs)[label]


def label_for_id(pairs: list[tuple[str, str]], id_: str) -> str:
    """Map a domain id to its display label (falls back to the id)."""
    return {domain_id: label for label, domain_id in pairs}.get(id_, id_)


def technique_options() -> list[tuple[str, str]]:
    """Return ``(technique_id, name)`` pairs from the prompt registry."""
    return registry.selector_options()


def difficulty_default_index() -> int:
    """Index of the 'Medium' difficulty option (a sensible default)."""
    return [domain_id for _, domain_id in DIFFICULTIES].index("moderate")


# --- Cost formatting ---------------------------------------------------------


def format_usd(value: float | None) -> str:
    """Format a USD cost for display, or an em dash when unavailable."""
    if value is None:
        return "—"
    return f"${value:,.6f}"


# --- Report serialization ----------------------------------------------------


def report_to_json(report: FinalInterviewReport) -> str:
    """Serialise the final report to pretty JSON."""
    return report.model_dump_json(indent=2)


def _md_list(title: str, items: list[str]) -> str:
    lines = [f"### {title}", ""]
    lines.extend(f"- {item}" for item in items)
    lines.append("")
    return "\n".join(lines)


def report_to_markdown(
    report: FinalInterviewReport,
    config: InterviewConfiguration | None = None,
) -> str:
    """Render the final report as readable Markdown for download."""
    header = ["# Interview readiness report", ""]
    if config is not None:
        header.append(
            f"**Target role:** {config.target_role}  "
            f"\n**Sector:** {config.industry_or_sector}  "
            f"\n**Career level:** {label_for_id(CAREER_LEVELS, config.career_level)}"
        )
        header.append("")
    header.append(
        f"**Readiness score:** {report.overall_readiness_score}/100 "
        "_(practice guidance only — not an employment decision)_"
    )
    header.append("")
    header.append("## Performance summary")
    header.append("")
    header.append(report.performance_summary)
    header.append("")

    sections = [
        ("Strongest competencies", report.strongest_competencies),
        ("Development priorities", report.development_priorities),
        ("Recurring answer patterns", report.recurring_answer_patterns),
        ("Evidence gaps", report.evidence_gaps),
        ("Highest-risk questions", report.highest_risk_questions),
        ("Recommended practice actions", report.recommended_practice_actions),
        ("Final interview checklist", report.final_interview_checklist),
    ]
    body = "\n".join(_md_list(title, items) for title, items in sections)
    return "\n".join(header) + "\n" + body


# --- Validation helpers used by app.py --------------------------------------


def all_option_ids_valid() -> bool:
    """Sanity check: every catalogue id exists in the domain vocabularies.

    Used by tests to guarantee UI options never produce an invalid config.
    """
    checks = [
        (CAREER_LEVELS, constants.CAREER_LEVELS),
        (INTERVIEW_TYPES, constants.INTERVIEW_TYPES),
        (PERSONAS, constants.INTERVIEWER_PERSONAS),
        (DIFFICULTIES, constants.DIFFICULTY_LEVELS),
        (RESPONSE_DETAILS, constants.RESPONSE_DETAIL_LEVELS),
    ]
    for pairs, allowed in checks:
        for _, domain_id in pairs:
            if domain_id not in allowed:
                return False
    if any(model not in constants.APPROVED_MODELS for model in MODELS):
        return False
    rubric_fields = set(AnswerEvaluation.model_fields)
    return all(field in rubric_fields for field, _ in RUBRIC_CRITERIA)
