"""The `PreparationContext` contract — the career → interview handoff payload.

Plain domain data only, so it is safe to store in Streamlit session state, log
(structurally), and hand to the Interview module. It never carries Chroma
objects, LangChain documents, retriever internals or OpenRouter objects.
Optional fields stay optional — we do not invent data to fill every field.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SourceReference", "PreparationContext"]

_MAX_ITEMS = 50
_MAX_ITEM_CHARS = 400
# Local bound so the integration package stays independent of either module.
_MAX_JOB_DESCRIPTION_CHARS = 12_000


class SourceReference(BaseModel):
    """A grounding reference (provenance), not scoring evidence."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=300)
    source: str | None = Field(default=None, max_length=500)
    page: int | None = Field(default=None, ge=0)


class PreparationContext(BaseModel):
    """Structured preparation context produced by Career Intelligence."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    # Role framing
    target_role: str = Field(min_length=1, max_length=200)
    industry: str | None = Field(default=None, max_length=200)
    company_context: str | None = Field(default=None, max_length=4_000)
    job_description: str | None = Field(
        default=None, max_length=_MAX_JOB_DESCRIPTION_CHARS
    )
    seniority: str | None = Field(default=None, max_length=100)

    # Requirements (from the Job Description Analyzer)
    required_skills: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)
    key_responsibilities: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)
    leadership_expectations: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)

    # Candidate fit (from the deterministic Gap Analyzer)
    candidate_strengths: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)
    candidate_gaps: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)

    # Interview focus
    likely_interview_topics: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)
    priority_competencies: list[str] = Field(default_factory=list, max_length=_MAX_ITEMS)

    # Provenance (grounding, not scoring)
    source_references: list[SourceReference] = Field(
        default_factory=list, max_length=_MAX_ITEMS
    )

    @property
    def source_count(self) -> int:
        return len(self.source_references)
