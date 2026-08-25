"""Career → Interview handoff: session storage, navigation and setup prefill.

The Career module stores a `PreparationContext`; the Interview module reads it
through :func:`interview_prefill` (plain data only). Navigation targets are set
via the shell's ``_pending_nav`` flag. Nothing here imports Career retrievers,
LangChain, Chroma or tool internals.
"""

from __future__ import annotations

from src.integration.models import PreparationContext

__all__ = [
    "PREP_CONTEXT_KEY",
    "store_context",
    "get_context",
    "has_context",
    "clear_context",
    "request_practice",
    "request_return_to_preparation",
    "interview_prefill",
    "preview",
    "seniority_to_career_level",
    "seniority_to_difficulty",
]

PREP_CONTEXT_KEY = "integration.prep_context"
_PENDING_NAV_KEY = "_pending_nav"
_NAV_INTERVIEW = "Interview Practice"
_NAV_CAREER = "Career Intelligence"
_MAX_BACKGROUND_CHARS = 6_000


# --- Session state -----------------------------------------------------------


def store_context(session_state, context: PreparationContext) -> None:
    session_state[PREP_CONTEXT_KEY] = context


def get_context(session_state) -> PreparationContext | None:
    value = session_state.get(PREP_CONTEXT_KEY)
    return value if isinstance(value, PreparationContext) else None


def has_context(session_state) -> bool:
    return get_context(session_state) is not None


def clear_context(session_state) -> None:
    session_state.pop(PREP_CONTEXT_KEY, None)


# --- Navigation --------------------------------------------------------------


def request_practice(session_state, context: PreparationContext) -> None:
    """Store the context and queue navigation to Interview Practice."""
    store_context(session_state, context)
    session_state[_PENDING_NAV_KEY] = _NAV_INTERVIEW


def request_return_to_preparation(session_state) -> None:
    """Queue navigation back to Career Intelligence (context is preserved)."""
    session_state[_PENDING_NAV_KEY] = _NAV_CAREER


# --- Mapping to the interview taxonomy (generic ids only) --------------------


def seniority_to_career_level(seniority: str | None) -> str | None:
    """Map free-text seniority to an interview career-level id, or None."""
    if not seniority:
        return None
    s = seniority.lower()
    if "intern" in s or "apprentice" in s:
        return "internship"
    if any(w in s for w in ("entry", "junior", "graduate", "trainee")):
        return "entry"
    if any(w in s for w in ("chief", "c-level", "executive", "vp", "vice president", "cxo")):
        return "executive"
    if any(w in s for w in ("director", "head of")):
        return "director"
    if "manager" in s or "lead" in s:
        return "manager"
    if any(w in s for w in ("senior", "principal", "staff", "sr")):
        return "senior"
    return "mid"


def seniority_to_difficulty(seniority: str | None) -> str | None:
    """Map seniority to a difficulty id (higher seniority → harder), or None."""
    level = seniority_to_career_level(seniority)
    if level in ("executive", "director", "senior"):
        return "hard"
    if level in ("internship", "entry"):
        return "easy"
    if level is None:
        return None
    return "moderate"


# --- Interview consumer helpers ---------------------------------------------


def _compose_background(context: PreparationContext) -> str:
    parts: list[str] = []
    if context.candidate_strengths:
        parts.append("Strengths: " + "; ".join(context.candidate_strengths) + ".")
    if context.candidate_gaps:
        parts.append("Development areas: " + "; ".join(context.candidate_gaps) + ".")
    return " ".join(parts)[:_MAX_BACKGROUND_CHARS]


def interview_prefill(session_state) -> dict:
    """Return setup defaults from the stored context (plain data), or ``{}``.

    Values are *defaults* the candidate can review and edit — nothing here starts
    an interview. Career-level and difficulty are returned as generic taxonomy
    ids; the interview UI maps them to its own labels.
    """
    context = get_context(session_state)
    if context is None:
        return {}
    return {
        "target_role": context.target_role,
        "industry": context.industry or "",
        "career_level": seniority_to_career_level(context.seniority),
        "company_context": context.company_context or "",
        "job_description": context.job_description or "",
        "candidate_background": _compose_background(context),
        "difficulty": seniority_to_difficulty(context.seniority),
        "source_count": context.source_count,
    }


def preview(context: PreparationContext) -> dict:
    """A short, safe preview for the 'Practise this role' card."""
    return {
        "role": context.target_role,
        "seniority": context.seniority or "—",
        "top_competencies": context.priority_competencies[:5],
        "priority_gaps": context.candidate_gaps[:5],
        "likely_themes": context.likely_interview_topics[:5],
    }
