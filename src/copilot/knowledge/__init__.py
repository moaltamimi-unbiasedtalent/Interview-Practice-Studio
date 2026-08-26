"""Multi-source knowledge architecture for Career Intelligence.

Career questions are routed to the right lane instead of always going to vector
search:

* **Structured Role DB** — occupations/skills/tasks from taxonomies (ESCO, O*NET,
  ISCO, KldB), normalised into a small SQLite repository.
* **Vector Knowledge** — narrative documents (methodology, market reports,
  competency frameworks) in Chroma (the existing RAG store).
* **Compensation DB** — structured pay statistics (Entgeltatlas, OEWS, ASHE,
  Eurostat) with strict context (currency, period, statistic, geography, year).

Everything carries :class:`~src.copilot.knowledge.provenance.Provenance`, and a
:mod:`~src.copilot.knowledge.router` decides the lane. Nothing here changes
Interview Practice.
"""

from src.copilot.knowledge.provenance import AuthorityLevel, Provenance
from src.copilot.knowledge.router import (
    RetrievalLane,
    route_question,
    source_priority,
    detect_country,
)
from src.copilot.knowledge.status import SourceStatus, compute_status, summary

__all__ = [
    "Provenance",
    "AuthorityLevel",
    "RetrievalLane",
    "route_question",
    "source_priority",
    "detect_country",
    "SourceStatus",
    "compute_status",
    "summary",
]
