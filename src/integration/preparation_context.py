"""Build a `PreparationContext` from existing Career Intelligence outputs.

Pure assembly of already-computed structured results (Job Description Analyzer,
Candidate Gap Analyzer, retrieved evidence). It makes **no** LLM call — it only
reshapes data that already exists into the handoff contract.
"""

from __future__ import annotations

from src.integration.models import PreparationContext, SourceReference

__all__ = ["build_preparation_context", "resolve_target_role"]

_MAX_ITEMS = 50
_MAX_ITEM_CHARS = 400
_MAX_ROLE_CHARS = 200


def resolve_target_role(
    *,
    user_confirmed_role: str | None = None,
    role_requirements=None,
    resolved_occupation: str | None = None,
) -> str:
    """Deterministically pick the handoff target role — never fabricated.

    Precedence: (1) an explicit user-confirmed role, (2) the Job Description
    Analyzer's ``role_title``, (3) a structured resolved occupation, else "".
    Values are trimmed and length-bounded. No LLM call, no answer-text parsing,
    no placeholder substitution.
    """
    role_title = getattr(role_requirements, "role_title", None) if role_requirements else None
    for candidate in (user_confirmed_role, role_title, resolved_occupation):
        role = (str(candidate).strip() if candidate else "")
        if role:
            return role[:_MAX_ROLE_CHARS]
    return ""


def _clean_list(values, limit: int = _MAX_ITEMS) -> list[str]:
    """De-duplicate, trim and bound a list of strings (order preserved)."""
    out: list[str] = []
    seen: set[str] = set()
    for value in values or []:
        text = (str(value) or "").strip()[:_MAX_ITEM_CHARS]
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
        if len(out) >= limit:
            break
    return out


def _reference_fields(result) -> tuple:
    """Extract ``(title, source, page)`` from a retrieval or knowledge-evidence
    item, without coupling to Chroma/LangChain internals.

    Supports both ``RetrievalResult`` (``title``/``source``/``page`` properties)
    and structured ``KnowledgeEvidence`` (``source_title``/``source_url`` +
    ``occupation_title``). Only plain scalars are read.
    """
    title = (getattr(result, "title", None)
             or getattr(result, "source_title", None)
             or getattr(result, "occupation_title", None))
    source = (getattr(result, "source", None)
              or getattr(result, "source_url", None)
              or getattr(result, "source_id", None))
    page = getattr(result, "page", None)
    if not isinstance(page, int):
        page = None
    return title, source, page


def _source_references(evidence) -> list[SourceReference]:
    refs: list[SourceReference] = []
    seen: set[tuple] = set()
    for result in evidence or []:
        title, source, page = _reference_fields(result)
        key = (title, source, page)
        if key in seen or not (title or source):
            continue
        seen.add(key)
        refs.append(SourceReference(title=title, source=source, page=page))
        if len(refs) >= _MAX_ITEMS:
            break
    return refs


def build_preparation_context(
    *,
    role_requirements=None,
    gap_result=None,
    evidence=None,
    target_role: str | None = None,
    industry: str | None = None,
    company_context: str | None = None,
    job_description: str | None = None,
) -> PreparationContext:
    """Assemble a `PreparationContext` from available Career results.

    Any input may be missing; only ``target_role`` (explicit or from the role
    requirements) is required. No field is invented to look complete.
    """
    rr = role_requirements
    gap = gap_result

    role = resolve_target_role(user_confirmed_role=target_role, role_requirements=rr)
    if not role:
        raise ValueError("A target role is required to build a PreparationContext.")

    required_skills = _clean_list(getattr(rr, "required_skills", []) if rr else [])
    key_responsibilities = _clean_list(getattr(rr, "key_responsibilities", []) if rr else [])
    leadership = _clean_list(getattr(rr, "leadership_expectations", []) if rr else [])
    likely_topics = _clean_list(getattr(rr, "likely_interview_themes", []) if rr else [])

    strengths = _clean_list(getattr(gap, "strengths", []) if gap else [])
    if gap is not None:
        gap_items = [g.requirement for g in getattr(gap, "priority_gaps", [])] or getattr(
            gap, "missing", []
        )
    else:
        gap_items = []
    gaps = _clean_list(gap_items)

    # Priority competencies: high-severity gaps first, then required skills.
    high_priority = (
        [g.requirement for g in getattr(gap, "priority_gaps", []) if g.severity == "high"]
        if gap is not None
        else []
    )
    priority_competencies = _clean_list(list(high_priority) + list(required_skills))

    return PreparationContext(
        target_role=role[:200],
        industry=(industry or None),
        company_context=(company_context or None),
        job_description=(job_description or None),
        seniority=(getattr(rr, "seniority", None) if rr else None),
        required_skills=required_skills,
        key_responsibilities=key_responsibilities,
        leadership_expectations=leadership,
        candidate_strengths=strengths,
        candidate_gaps=gaps,
        likely_interview_topics=likely_topics,
        priority_competencies=priority_competencies,
        source_references=_source_references(evidence),
    )
