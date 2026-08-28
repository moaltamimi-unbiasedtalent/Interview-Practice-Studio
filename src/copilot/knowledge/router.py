"""Deterministic retrieval router: pick the knowledge lane for a question.

Obvious intents route deterministically (keyword rules); an optional LLM
classifier is only consulted when the deterministic signal is ambiguous. Nothing
is sent blindly to vector search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.copilot import constants

__all__ = ["RetrievalLane", "RouteDecision", "route_question", "source_priority", "detect_country"]


class RetrievalLane:
    STRUCTURED_ROLE = constants.LANE_STRUCTURED_ROLE
    VECTOR = constants.LANE_VECTOR
    COMPENSATION = constants.LANE_COMPENSATION
    FORECAST = constants.LANE_FORECAST
    MIXED = constants.LANE_MIXED
    COMPETENCY = constants.LANE_COMPETENCY
    CYBERSECURITY = constants.LANE_CYBERSECURITY
    SHORTAGE = constants.LANE_SHORTAGE
    OPENINGS = constants.LANE_OPENINGS
    SENIORITY = constants.LANE_SENIORITY
    TRANSITION = constants.LANE_TRANSITION


@dataclass
class RouteDecision:
    lane: str
    reason: str
    confidence: float = 1.0


_COMP = re.compile(r"\b(salary|salaries|earn|earns|earning|pay|paid|wage|wages|compensation|income|remuneration|how much)\b", re.I)
_ROLE = re.compile(
    r"\b(responsibilities|duties|tasks|day.to.day|role of)\b|what\s+(?:does|do)\s+.*\bdo\b",
    re.I,
)
_SKILL = re.compile(r"\b(skills?|competenc|capabilit|knowledge|proficienc)\b", re.I)
_TREND = re.compile(r"\b(demand|grow|growth|growing|outlook|trend|trends|future|forecast|projected|decline)\b", re.I)

# New, more specific lanes. These are checked BEFORE the generic role/skill/trend
# rules, but each is written narrowly so existing generic queries still route as
# before (e.g. "what skills do cybersecurity analysts need?" stays structured_role).
_TRANSITION = re.compile(
    r"\b(transition|transitioning|switch|switching|move|moving|pivot|change career|career change|from\s+.+\s+to)\b.*\b(role|career|job|into|to)\b",
    re.I,
)
_SHORTAGE = re.compile(r"\b(shortage|shortages|hard[- ]to[- ]fill|talent gap|skills gap|bottleneck occupation)\b", re.I)
_OPENINGS = re.compile(r"\b(job openings|openings|vacancies|replacement demand|how many (?:jobs|roles|positions))\b", re.I)
_CYBER = re.compile(
    r"\b(cyber ?security|cyber|information security|infosec)\b.*\b(responsibilit|task|duties|work role|incident|framework|nice)"
    r"|\bincident respon(?:se|der|ders|ding)\b",
    re.I,
)
_DIGITAL = re.compile(r"\b(digital)\b.*\b(competenc|capabilit|literac|skill)", re.I)
_SENIORITY = re.compile(
    r"\b(behaviours?|leadership expectation|seniority|success profile|grade|career level|what makes a (?:senior|junior|lead|principal))\b",
    re.I,
)

# Country detection for geographic source precedence.
_COUNTRY_PATTERNS = {
    "DE": re.compile(r"\b(germany|german|deutschland|berlin|munich|kldb|berufenet)\b", re.I),
    "UK": re.compile(r"\b(uk|united kingdom|britain|british|england|scotland|wales|ashe|civil service)\b", re.I),
    "US": re.compile(r"\b(us|u\.s\.|usa|united states|america|american|federal)\b", re.I),
    "EU": re.compile(r"\b(eu|europe|european|eurozone|esco|cedefop|eurostat)\b", re.I),
}


def detect_country(query: str) -> str | None:
    """Best-effort country/region code from the question, or None if unspecified."""
    text = query or ""
    # Prefer the most specific national signals before the broader EU signal.
    for code in ("DE", "UK", "US", "EU"):
        if _COUNTRY_PATTERNS[code].search(text):
            return code
    return None


def source_priority(country: str | None) -> list[str]:
    """Ordered source ids to prefer for a country-specific question.

    Country-specific official statistics outrank generic international material;
    an unknown country returns the EU/international default order.
    """
    if country and country in constants.COUNTRY_SOURCE_PRIORITY:
        return list(constants.COUNTRY_SOURCE_PRIORITY[country])
    return list(constants.COUNTRY_SOURCE_PRIORITY["EU"])


def route_question(query: str, llm_classifier=None) -> RouteDecision:
    """Return the retrieval lane for ``query``.

    ``llm_classifier`` (optional) is a callable ``str -> lane`` used only when the
    deterministic rules are ambiguous.
    """
    text = query or ""

    # Specific lanes first (narrowly scoped so they don't shadow generic queries).
    if _TRANSITION.search(text):
        return RouteDecision(RetrievalLane.TRANSITION, "career transition comparison", 0.85)
    if _SHORTAGE.search(text):
        return RouteDecision(RetrievalLane.SHORTAGE, "labour/skills shortage terms", 0.9)
    if _OPENINGS.search(text):
        return RouteDecision(RetrievalLane.OPENINGS, "job openings / replacement demand", 0.9)
    if _CYBER.search(text):
        return RouteDecision(RetrievalLane.CYBERSECURITY, "cybersecurity work-role terms (NICE)", 0.85)
    if _DIGITAL.search(text):
        return RouteDecision(RetrievalLane.COMPETENCY, "digital competency terms (DigComp)", 0.8)

    comp = bool(_COMP.search(text))
    role = bool(_ROLE.search(text))
    skill = bool(_SKILL.search(text))
    trend = bool(_TREND.search(text))
    seniority = bool(_SENIORITY.search(text))

    # Compensation combined with role/skill → mixed (e.g. "skills and pay").
    if comp and (role or skill):
        return RouteDecision(RetrievalLane.MIXED, "compensation + role/skill terms", 0.9)
    if comp:
        return RouteDecision(RetrievalLane.COMPENSATION, "compensation terms", 0.95)
    if trend:
        return RouteDecision(RetrievalLane.FORECAST, "labour-market trend terms", 0.85)
    if seniority and not role and not skill:
        return RouteDecision(RetrievalLane.SENIORITY, "seniority/behaviour framework terms", 0.8)
    if role:
        return RouteDecision(RetrievalLane.STRUCTURED_ROLE, "role/responsibility terms", 0.9)
    if skill:
        return RouteDecision(RetrievalLane.STRUCTURED_ROLE, "skill terms (structured + vector context)", 0.7)

    # Ambiguous: consult the LLM classifier if provided, else default to vector.
    if llm_classifier is not None:
        try:
            lane = llm_classifier(text)
            if lane in constants.RETRIEVAL_LANES:
                return RouteDecision(lane, "llm disambiguation", 0.6)
        except Exception:  # pragma: no cover - classifier must never break routing
            pass
    return RouteDecision(RetrievalLane.VECTOR, "default narrative/vector", 0.5)
