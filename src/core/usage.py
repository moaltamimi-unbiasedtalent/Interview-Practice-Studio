"""Consolidated token/cost usage records across both modules.

One :class:`UsageRecord` type, tagged by :class:`Operation`, so career and
interview usage are counted consistently and separately. :class:`UsageLedger`
aggregates without double-counting (records with the same id are counted once).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from src.copilot import constants as _constants

__all__ = ["Operation", "UsageRecord", "UsageLedger"]


class Operation(str, Enum):
    """The operation/source a usage record is attributed to."""

    CAREER_QUERY_TRANSLATION = "career_query_translation"
    CAREER_FINAL_GENERATION = "career_final_generation"
    CAREER_TOOLS = "career_tools"
    INTERVIEW_STRATEGY = "interview_strategy"
    INTERVIEW_QUESTION = "interview_question"
    INTERVIEW_EVALUATION = "interview_evaluation"
    INTERVIEW_REPORT = "interview_report"
    SPEECH_TRANSCRIPTION = "speech_transcription"
    GEMINI_LIVE = "gemini_live"


class UsageRecord(BaseModel):
    """Token usage + cost for one operation (no content, safe to log/aggregate)."""

    operation: Operation
    model: str = ""
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    cost_usd: float | None = Field(default=None, ge=0)
    currency: str = _constants.DEFAULT_CURRENCY
    # Optional stable id used for de-duplication (e.g. an OpenRouter request id).
    id: str | None = None


class UsageLedger:
    """Aggregate usage records with no double-counting."""

    def __init__(self) -> None:
        self._records: dict[str, UsageRecord] = {}
        self._order: list[str] = []

    def add(self, record: UsageRecord) -> bool:
        """Add a record; return False if it was a duplicate (ignored)."""
        key = record.id or f"auto-{len(self._order)}"
        if key in self._records:
            return False
        self._records[key] = record
        self._order.append(key)
        return True

    @property
    def records(self) -> list[UsageRecord]:
        return [self._records[key] for key in self._order]

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self.records)

    @property
    def total_cost_usd(self) -> float:
        return sum(r.cost_usd or 0.0 for r in self.records)

    def tokens_by_source(self) -> dict[str, int]:
        """Total tokens grouped by operation (career vs interview isolation)."""
        totals: dict[str, int] = {}
        for record in self.records:
            totals[record.operation.value] = (
                totals.get(record.operation.value, 0) + record.total_tokens
            )
        return totals
