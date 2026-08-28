"""Company & opportunity context models.

Time-sensitive, candidate-supplied research about a specific employer — kept
strictly separate from the permanent occupational knowledge base. Everything here
is plain data (safe for session state, PreparationContext and logging); no raw
crawler objects, file handles or private uploads are carried.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["CompanySource", "CompanyContext", "SOURCE_TYPES"]

# Preferred/official source types, most-authoritative first.
SOURCE_TYPES = (
    "official_website",
    "careers",
    "investor_relations",
    "annual_report",
    "regulatory_filing",
    "press_release",
    "uploaded_document",
    "other",
)

_MAX = 40
_MAX_CHARS = 600


class CompanySource(BaseModel):
    """A provenance reference for one company page or uploaded document."""

    model_config = ConfigDict(str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=300)
    url: str | None = Field(default=None, max_length=1000)
    source_type: str = Field(default="other")
    publication_date: str | None = Field(default=None, max_length=40)
    retrieved_at: str | None = Field(default=None, max_length=40)
    trust: str = Field(default="provided")  # official | provided | unknown


class CompanyContext(BaseModel):
    """Evidence-grounded, time-stamped context about a target employer."""

    model_config = ConfigDict(str_strip_whitespace=True)

    company_name: str = Field(min_length=1, max_length=200)
    official_website: str | None = Field(default=None, max_length=1000)
    career_page: str | None = Field(default=None, max_length=1000)
    industry: str | None = Field(default=None, max_length=200)
    company_description: str | None = Field(default=None, max_length=2000)
    products_services: list[str] = Field(default_factory=list, max_length=_MAX)
    values: list[str] = Field(default_factory=list, max_length=_MAX)
    recent_official_updates: list[str] = Field(default_factory=list, max_length=_MAX)
    annual_report_sources: list[CompanySource] = Field(default_factory=list, max_length=_MAX)
    investor_relations_sources: list[CompanySource] = Field(default_factory=list, max_length=_MAX)
    provided_job_description: str | None = Field(default=None, max_length=12_000)
    source_references: list[CompanySource] = Field(default_factory=list, max_length=_MAX)
    retrieved_at: str | None = Field(default=None, max_length=40)
    notes: list[str] = Field(default_factory=list, max_length=_MAX)

    @property
    def has_evidence(self) -> bool:
        return bool(self.company_description or self.products_services or self.values
                    or self.recent_official_updates or self.source_references)

    def safe_summary(self, *, max_chars: int = 1800) -> str:
        """A bounded plain-text summary — safe for synthesis / PreparationContext.

        Carries only summarised, provenance-tagged context (never raw documents),
        and always states the ``retrieved_at`` time so recency is explicit.
        """
        parts: list[str] = [f"Company: {self.company_name}"]
        if self.industry:
            parts.append(f"Industry: {self.industry}")
        if self.company_description:
            parts.append(f"About: {self.company_description[:_MAX_CHARS]}")
        if self.products_services:
            parts.append("Products/services: " + "; ".join(self.products_services[:8]))
        if self.values:
            parts.append("Stated values: " + "; ".join(self.values[:8]))
        if self.recent_official_updates:
            parts.append("Recent official updates: "
                         + " | ".join(self.recent_official_updates[:6]))
        else:
            parts.append("Recent official updates: none provided (do not invent any).")
        srcs = [s.url or s.title for s in self.source_references if (s.url or s.title)]
        if srcs:
            parts.append("Sources: " + "; ".join(str(s) for s in srcs[:8]))
        parts.append(f"Retrieved at: {self.retrieved_at or 'unknown'} "
                     "(company facts are time-sensitive).")
        return "\n".join(parts)[:max_chars]
