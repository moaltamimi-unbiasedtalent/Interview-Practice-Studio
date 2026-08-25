"""Structured career-transition comparison between two occupations.

Uses structured occupation data (skills, tasks, relationships) to compute shared
vs unique skills, transferable capabilities, key gaps and adjacent occupations.
It produces structured lists that feed the existing Candidate Gap Analyzer — it
does not duplicate the gap analysis or invent a match score.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

__all__ = ["OccupationComparison", "compare_occupations"]


class OccupationComparison(BaseModel):
    current_code: str
    target_code: str
    shared_skills: list[str] = Field(default_factory=list)
    unique_current_skills: list[str] = Field(default_factory=list)
    unique_target_skills: list[str] = Field(default_factory=list)
    related_tasks: list[str] = Field(default_factory=list)
    transferable_capabilities: list[str] = Field(default_factory=list)
    key_gaps: list[str] = Field(default_factory=list)
    related_occupations: list[str] = Field(default_factory=list)


def _skill_names(occ: dict) -> list[str]:
    out = []
    for s in occ.get("skills", []) or []:
        out.append(s["skill"] if isinstance(s, dict) else getattr(s, "name", str(s)))
    return out


def _norm(items):
    seen, out = set(), []
    for i in items:
        key = i.strip().lower()
        if key and key not in seen:
            seen.add(key); out.append(i.strip())
    return out


def compare_occupations(current: dict, target: dict) -> OccupationComparison:
    """Compare two occupation records (as returned by RoleRepository.get_occupation)."""
    cur_skills = _skill_names(current)
    tgt_skills = _skill_names(target)
    cur_l = {s.lower(): s for s in cur_skills}
    tgt_l = {s.lower(): s for s in tgt_skills}

    shared = [cur_l[k] for k in cur_l if k in tgt_l]
    unique_current = [cur_l[k] for k in cur_l if k not in tgt_l]
    unique_target = [tgt_l[k] for k in tgt_l if k not in cur_l]

    cur_tasks = set(t.lower() for t in current.get("tasks", []) or [])
    related_tasks = [t for t in (target.get("tasks", []) or []) if t.lower() in cur_tasks]

    related = [r["related_code"] if isinstance(r, dict) else getattr(r, "related_code", str(r))
               for r in (target.get("relationships", []) or [])]

    return OccupationComparison(
        current_code=current.get("occupation_code", ""),
        target_code=target.get("occupation_code", ""),
        shared_skills=_norm(shared),
        unique_current_skills=_norm(unique_current),
        unique_target_skills=_norm(unique_target),
        related_tasks=_norm(related_tasks),
        transferable_capabilities=_norm(shared + related_tasks),
        key_gaps=_norm(unique_target),  # what the target needs that the candidate lacks
        related_occupations=_norm(related),
    )
