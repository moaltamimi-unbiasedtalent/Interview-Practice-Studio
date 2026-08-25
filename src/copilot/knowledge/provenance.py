"""One provenance model for every structured record and vector chunk.

Authority level is retrieval/ranking metadata — **not** a truth score.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field

from src.copilot import constants

__all__ = ["AuthorityLevel", "Provenance", "authority_for_publisher"]


class AuthorityLevel:
    """Source-authority ranking (metadata, not truth)."""

    OFFICIAL = constants.AUTHORITY_OFFICIAL
    PUBLIC_FRAMEWORK = constants.AUTHORITY_PUBLIC_FRAMEWORK
    INDUSTRY = constants.AUTHORITY_INDUSTRY


# Known Level-1 / Level-2 publishers (lower-cased substrings) for classification.
_LEVEL_1 = (
    "european commission", "eurostat", "cedefop", "ilo", "o*net", "onet",
    "bureau of labor statistics", "bls", "bundesagentur für arbeit",
    "bundesagentur fur arbeit", "office for national statistics", "ons", "nist",
)
_LEVEL_2 = ("civil service", "digcomp", "eqf", "opm", "european qualifications")


def _matches(name: str, keywords) -> bool:
    # Word-boundary match so short acronyms (ons, bls) don't hit inside words.
    return any(re.search(r"\b" + re.escape(k) + r"\b", name) for k in keywords)


def authority_for_publisher(publisher: str | None) -> int:
    """Best-effort authority level from a publisher name (defaults to industry)."""
    name = (publisher or "").lower()
    if _matches(name, _LEVEL_1):
        return AuthorityLevel.OFFICIAL
    if _matches(name, _LEVEL_2):
        return AuthorityLevel.PUBLIC_FRAMEWORK
    return AuthorityLevel.INDUSTRY


class Provenance(BaseModel):
    """Shared provenance carried by structured records and vector chunks."""

    model_config = ConfigDict(str_strip_whitespace=True)

    source_id: str
    source_title: str
    source_type: str
    authority_level: int = Field(default=AuthorityLevel.INDUSTRY, ge=1, le=3)
    publisher: str | None = None
    country: str | None = None
    language: str | None = None
    version: str | None = None
    reference_year: int | None = None
    licence: str | None = None
    source_url: str | None = None
    retrieval_date: str | None = None
    content_type: str = "structured"

    # Role-specific (optional).
    occupation_code: str | None = None
    occupation_title: str | None = None
    isco_code: str | None = None

    # Compensation-specific (optional).
    currency: str | None = None
    pay_period: str | None = None
    statistic: str | None = None
    geography: str | None = None

    def label(self) -> str:
        """Short, safe provenance label for display."""
        parts = [self.source_title]
        if self.reference_year:
            parts.append(str(self.reference_year))
        if self.geography:
            parts.append(self.geography)
        return " · ".join(parts)
