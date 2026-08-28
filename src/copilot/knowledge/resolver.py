"""Occupation resolution: map a natural question to structured occupations.

Turns "What does a Senior Product Manager earn in Germany?" into candidate
occupations from the RoleRepository, handling aliases (HRBP → HR Business
Partner), punctuation, seniority prefixes and source crosswalks (SOC/ISCO/ESCO/
KldB). It never silently picks between genuinely different occupations — when the
result is ambiguous it returns the ranked candidates so the caller can ask the
user to clarify.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from src.copilot.knowledge.router import source_priority

__all__ = [
    "OccupationCandidate", "ResolvedOccupation",
    "extract_occupation_phrase", "resolve_occupation", "title_variants",
]


# Common alias / synonym expansions (bidirectional intent). Kept small and
# profession-neutral; extend as needed.
_ALIASES = {
    "hrbp": "hr business partner",
    "hr manager": "human resources manager",
    "hr business partner": "human resources business partner",
    "hr director": "human resources director",
    "people director": "human resources director",
    "people partner": "human resources business partner",
    "swe": "software engineer",
    "sw engineer": "software engineer",
    "software developer": "software engineer",
    "developer": "software developer",
    "pm": "product manager",
    "ba": "business analyst",
    "devops": "devops engineer",
    "sre": "site reliability engineer",
    "nursing": "nurse",
}

# Seniority prefixes to strip when matching a base occupation.
_SENIORITY = re.compile(
    r"^\s*(senior|junior|lead|principal|staff|chief|head of|deputy|associate|"
    r"entry[- ]level|graduate|trainee|mid[- ]level)\s+",
    re.I,
)

# Optional article ("a"/"an"/"the") with a real word boundary so "an HR" does
# not leave a dangling "n".
_ART = r"(?:(?:an?|the)\s+)?"

# Question scaffolding to remove when extracting the occupation phrase.
_PATTERNS = [
    re.compile(rf"what (?:does|do) {_ART}(.+?)\s+(?:do|earn|need|require|make)\b", re.I),
    re.compile(rf"(?:responsibilities|duties|tasks|role) of {_ART}(.+?)[\?\.]?$", re.I),
    re.compile(rf"skills? (?:for|of|does|do)\s+{_ART}(.+?)\s+(?:need|require|have)\b", re.I),
    re.compile(rf"(?:salary|pay|wage|compensation|earnings?) (?:for|of)\s+{_ART}(.+?)(?:\s+in\b|[\?\.]?$)", re.I),
    re.compile(rf"(?:how much (?:does|do))\s+{_ART}(.+?)\s+(?:earn|make|get paid)", re.I),
    re.compile(rf"(?:what is|what's) {_ART}(.+?)\s+(?:salary|pay)", re.I),
    re.compile(rf"(?:is|are)\s+{_ART}(.+?)\s+(?:in shortage|expected to|forecast)", re.I),
    re.compile(rf"(?:openings?|vacancies|demand|shortage|forecast|outlook)\b.*?\bfor\s+{_ART}(.+?)[\?\.]?$", re.I),
]

# Country/qualifier words to trim off a captured phrase tail.
_TRAILING = re.compile(
    r"\b(in|the|us|usa|u\.s\.|uk|united states|united kingdom|germany|europe|eu|"
    r"typically|usually|role|position|job|occupation)\b.*$",
    re.I,
)


class OccupationCandidate(BaseModel):
    occupation_code: str
    title: str
    source_id: str
    score: float = 0.0


class ResolvedOccupation(BaseModel):
    phrase: str = ""
    candidates: list[OccupationCandidate] = Field(default_factory=list)
    ambiguous: bool = False

    @property
    def best(self) -> OccupationCandidate | None:
        return self.candidates[0] if self.candidates else None


def _clean(text: str) -> str:
    text = re.sub(r"[^\w\s&/+-]", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def extract_occupation_phrase(query: str) -> str:
    """Best-effort occupation phrase from a natural-language question."""
    q = (query or "").strip()
    for pat in _PATTERNS:
        m = pat.search(q)
        if m:
            phrase = _TRAILING.sub("", m.group(1)).strip()
            if phrase:
                return _clean(phrase)
    # Fallback: strip common lead-ins and trailing qualifiers.
    q = re.sub(r"^(what|which|how|tell me about|describe|explain)\b.*?\b(a|an|the)\b", "", q, flags=re.I)
    q = _TRAILING.sub("", q)
    return _clean(q)


def title_variants(phrase: str) -> list[str]:
    """Public alias for :func:`_normalise` — search variants for a title phrase."""
    return _normalise(phrase)


def _normalise(phrase: str) -> list[str]:
    """Return search variants for a phrase (alias-expanded, seniority-stripped)."""
    base = phrase.strip().lower()
    variants = [base]
    if base in _ALIASES:
        variants.append(_ALIASES[base])
    stripped = _SENIORITY.sub("", base).strip()
    if stripped and stripped != base:
        variants.append(stripped)
        if stripped in _ALIASES:
            variants.append(_ALIASES[stripped])
    # Naive singularisation so "nurses"/"analysts" match singular titles.
    for v in list(variants):
        if len(v) > 3 and v.endswith("s") and not v.endswith("ss"):
            variants.append(v[:-1])
    # De-duplicate, keep order.
    seen, out = set(), []
    for v in variants:
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out


def resolve_occupation(repo, query: str, *, country: str | None = None,
                       limit: int = 5) -> ResolvedOccupation:
    """Resolve an occupation from ``query`` using the role repository.

    Candidates are ranked by source precedence for ``country`` (national official
    sources first), then by how closely the title matches the phrase. Ambiguity is
    reported rather than resolved silently.
    """
    phrase = extract_occupation_phrase(query)
    if not phrase or repo is None:
        return ResolvedOccupation(phrase=phrase)

    priority = source_priority(country)

    def _src_rank(sid: str) -> int:
        base = sid.split(":", 1)[0] if sid else sid
        return priority.index(base) if base in priority else len(priority)

    seen: dict[tuple, OccupationCandidate] = {}
    for variant in _normalise(phrase):
        for row in repo.search(variant, limit=limit * 4):
            title = row.get("title", "")
            sid = row.get("source_id", "")
            key = (title.lower(), sid)
            if key in seen:
                continue
            tl = title.lower()
            # Simple lexical closeness: exact > startswith > contains.
            if tl == variant:
                match = 3.0
            elif tl.startswith(variant) or variant.startswith(tl):
                match = 2.0
            else:
                match = 1.0
            score = match - _src_rank(sid) * 0.1
            seen[key] = OccupationCandidate(
                occupation_code=row.get("occupation_code", ""),
                title=title, source_id=sid, score=score,
            )

    candidates = sorted(seen.values(), key=lambda c: (-c.score, c.title))[:limit]
    # Ambiguous when the top candidates are materially different occupations
    # (distinct base titles) at a comparable score.
    distinct_titles = {re.sub(r"s$", "", c.title.lower()) for c in candidates}
    ambiguous = (
        len(candidates) > 1
        and len(distinct_titles) > 1
        and abs(candidates[0].score - candidates[1].score) < 0.25
    )
    return ResolvedOccupation(phrase=phrase, candidates=candidates, ambiguous=ambiguous)
