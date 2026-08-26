"""Combined session export across both modules (plain data only).

Assembles a single JSON-able payload from already-safe pieces — a preparation
summary, Career sources, the Career conversation, and the interview summary /
report. It never includes prompts or secrets, and it stays decoupled: inputs are
accepted as Pydantic models (via ``model_dump``) or plain dicts.
"""

from __future__ import annotations

import json

__all__ = ["combined_session_export", "combined_session_json"]


def _to_dict(value):
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return None


def _career_sources(career_history: dict | None) -> list[dict]:
    """Unique citation references across the Career conversation."""
    if not career_history:
        return []
    seen: set[tuple] = set()
    sources: list[dict] = []
    for turn in career_history.get("turns", []):
        for citation in turn.get("citations", []):
            key = (citation.get("title"), citation.get("source"), citation.get("page"))
            if key in seen or not any(key):
                continue
            seen.add(key)
            sources.append(
                {
                    "title": citation.get("title"),
                    "source": citation.get("source"),
                    "page": citation.get("page"),
                }
            )
    return sources


def combined_session_export(
    *, preparation=None, career_history=None, interview_report=None
) -> dict:
    """Return a combined, safe session-export dict."""
    prep = _to_dict(preparation)
    history = _to_dict(career_history)
    report = _to_dict(interview_report)

    preparation_summary = None
    if prep:
        preparation_summary = {
            "target_role": prep.get("target_role"),
            "seniority": prep.get("seniority"),
            "priority_competencies": prep.get("priority_competencies", []),
            "likely_interview_topics": prep.get("likely_interview_topics", []),
            "source_count": len(prep.get("source_references", [])),
        }

    return {
        "preparation_summary": preparation_summary,
        "career_sources": _career_sources(history),
        "career_conversation": (history or {}).get("turns", []) if history else [],
        "interview_report": report,
    }


def combined_session_json(**kwargs) -> str:
    return json.dumps(combined_session_export(**kwargs), indent=2, ensure_ascii=False)
