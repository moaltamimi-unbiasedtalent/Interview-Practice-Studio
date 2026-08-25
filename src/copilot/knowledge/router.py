"""Deterministic retrieval router: pick the knowledge lane for a question.

Obvious intents route deterministically (keyword rules); an optional LLM
classifier is only consulted when the deterministic signal is ambiguous. Nothing
is sent blindly to vector search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.copilot import constants

__all__ = ["RetrievalLane", "RouteDecision", "route_question"]


class RetrievalLane:
    STRUCTURED_ROLE = constants.LANE_STRUCTURED_ROLE
    VECTOR = constants.LANE_VECTOR
    COMPENSATION = constants.LANE_COMPENSATION
    FORECAST = constants.LANE_FORECAST
    MIXED = constants.LANE_MIXED


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


def route_question(query: str, llm_classifier=None) -> RouteDecision:
    """Return the retrieval lane for ``query``.

    ``llm_classifier`` (optional) is a callable ``str -> lane`` used only when the
    deterministic rules are ambiguous.
    """
    text = query or ""
    comp = bool(_COMP.search(text))
    role = bool(_ROLE.search(text))
    skill = bool(_SKILL.search(text))
    trend = bool(_TREND.search(text))

    # Compensation combined with role/skill → mixed (e.g. "skills and pay").
    if comp and (role or skill):
        return RouteDecision(RetrievalLane.MIXED, "compensation + role/skill terms", 0.9)
    if comp:
        return RouteDecision(RetrievalLane.COMPENSATION, "compensation terms", 0.95)
    if trend:
        return RouteDecision(RetrievalLane.FORECAST, "labour-market trend terms", 0.85)
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
