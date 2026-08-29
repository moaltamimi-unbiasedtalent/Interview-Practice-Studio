"""Web-research provider interface for company context.

Live web search / page fetching is optional and behind this interface, so the
sprint requires no new paid provider. The default :class:`NullResearchProvider`
returns nothing (the app works entirely from user-supplied URLs and uploads).
A future provider (search API, official-page fetcher) implements the same ABC
and is injected — its returned text is still treated as untrusted.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class FetchedDocument:
    """A page/document returned by a provider (untrusted text)."""

    title: str
    text: str
    url: str | None = None
    publication_date: str | None = None
    source_type: str = "other"


class WebResearchProvider(ABC):
    """Fetches official company material. Implementations must be injectable."""

    name: str = "abstract"

    @abstractmethod
    def fetch(self, company_name: str, urls: list[str]) -> list[FetchedDocument]:
        """Return documents for the given company / URLs (may be empty)."""


class NullResearchProvider(WebResearchProvider):
    """No-op provider: performs no network access (the sprint default)."""

    name = "null"

    def fetch(self, company_name: str, urls: list[str]) -> list[FetchedDocument]:
        return []


__all__ = ["FetchedDocument", "WebResearchProvider", "NullResearchProvider"]
