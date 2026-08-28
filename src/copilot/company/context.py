"""Build a :class:`CompanyContext` from trusted, user-supplied inputs.

Inputs are: a company name, optional official/careers URLs, uploaded company
documents (annual report, investor deck, etc.) as extracted text, an optional job
description, and an optional (injected) web-research provider. Every URL is
validated and classified; every piece of text is treated as UNTRUSTED and scanned
for prompt injection (blocked text is dropped, flagged text kept with a note).
Nothing is fabricated — narrative fields are drawn only from provided material,
and recency is always stamped with ``retrieved_at``.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from src.copilot.company.models import CompanyContext, CompanySource
from src.copilot.company.provider import FetchedDocument, WebResearchProvider
from src.copilot.security import scan_text

__all__ = ["validate_url", "classify_source", "build_company_context"]

# Dates like "12 March 2026", "March 12, 2026", "2026-03-12", "Q1 2026".
_DATE_RE = re.compile(
    r"\b("
    r"\d{4}-\d{2}-\d{2}"
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}"
    r"|\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+\d{4}"
    r"|q[1-4]\s+\d{4}"
    r")\b",
    re.I,
)

_VALUE_HINTS = re.compile(r"\b(our values|we value|we believe|mission|our mission|"
                          r"integrity|customer(?:-| )?obsess|innovation|sustainab)", re.I)


def validate_url(url: str | None) -> str | None:
    """Return a normalised http(s) URL, or None if it is not a valid web URL."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if "://" not in url:
        url = "https://" + url  # tolerate bare domains
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return None
    if not parsed.netloc or "." not in parsed.netloc:
        return None
    return url


def _domain(url: str | None) -> str | None:
    if not url:
        return None
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def classify_source(url: str | None, *, official_domain: str | None = None,
                    is_upload: bool = False) -> str:
    """Classify a URL/document into a preferred source type."""
    if is_upload:
        return "uploaded_document"
    if not url:
        return "other"
    low = url.lower()
    host = _domain(url) or ""
    if "sec.gov" in low or re.search(r"\b(10-k|20-f|8-k|filing|edgar)\b", low):
        return "regulatory_filing"
    if "investor" in low or host.startswith("ir."):
        return "investor_relations"
    if "annual" in low and "report" in low:
        return "annual_report"
    if re.search(r"\b(career|careers|jobs|vacanc)\b", low):
        return "careers"
    if re.search(r"\b(press|news|newsroom|media)\b", low):
        return "press_release"
    if official_domain and _domain(url) == official_domain:
        return "official_website"
    return "other"


def _now(now: str | None) -> str:
    return now or datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _scan_ok(text: str, label: str, notes: list[str]) -> str | None:
    """Return cleaned text if safe/flagged, or None if it must be dropped."""
    scan = scan_text(text or "")
    if scan.blocked:
        notes.append(f"{label}: contained embedded instructions and was ignored for safety.")
        return None
    if scan.flagged:
        notes.append(f"{label}: flagged (kept as data, not instructions).")
    return text


def build_company_context(
    company_name: str,
    *,
    official_website: str | None = None,
    career_page: str | None = None,
    industry: str | None = None,
    documents: list[tuple[str, str]] | None = None,   # (title, extracted_text)
    job_description: str | None = None,
    provider: WebResearchProvider | None = None,
    now: str | None = None,
) -> CompanyContext:
    """Assemble a CompanyContext from trusted inputs. Never fabricates facts."""
    notes: list[str] = []
    retrieved_at = _now(now)
    official = validate_url(official_website)
    if official_website and not official:
        notes.append("Official website URL was not a valid http(s) URL and was ignored.")
    careers = validate_url(career_page)
    if career_page and not careers:
        notes.append("Careers URL was not a valid http(s) URL and was ignored.")
    official_domain = _domain(official)

    sources: list[CompanySource] = []
    annual: list[CompanySource] = []
    investor: list[CompanySource] = []

    def _add_source(title, url, is_upload=False, pub=None):
        stype = classify_source(url, official_domain=official_domain, is_upload=is_upload)
        src = CompanySource(
            title=title, url=url, source_type=stype, publication_date=pub,
            retrieved_at=retrieved_at,
            trust=("official" if (official_domain and _domain(url) == official_domain
                                  and not is_upload) else "provided"))
        sources.append(src)
        if stype == "annual_report":
            annual.append(src)
        elif stype == "investor_relations":
            investor.append(src)
        return src

    if official:
        _add_source(f"{company_name} — official website", official)
    if careers:
        _add_source(f"{company_name} — careers", careers)

    description = None
    products: list[str] = []
    values: list[str] = []
    recent: list[str] = []

    # Optional provider (default null) — its text is still untrusted.
    fetched: list[FetchedDocument] = []
    if provider is not None:
        try:
            fetched = provider.fetch(company_name, [u for u in (official, careers) if u]) or []
        except Exception:  # noqa: BLE001 - provider must never break the build
            notes.append(f"Research provider '{getattr(provider, 'name', '?')}' failed; "
                         "continued with supplied material only.")

    docs: list[tuple[str, str, str | None, str | None]] = []  # (title, text, url, pub)
    for title, text in (documents or []):
        docs.append((title, text, None, None))
    for fd in fetched:
        docs.append((fd.title, fd.text, fd.url, fd.publication_date))

    for title, text, url, pub in docs:
        safe = _scan_ok(text, f"Company document '{title}'", notes)
        if safe is None:
            continue
        src = _add_source(title, url, is_upload=(url is None), pub=pub)
        # Publication date: explicit, else first date found in the text.
        if not src.publication_date:
            m = _DATE_RE.search(safe)
            if m:
                src.publication_date = m.group(0)
        # Description: first substantive paragraph of the first document.
        if description is None:
            first = _clean(safe)[:1200]
            if first:
                description = first
        # Values: lines that look like values/mission statements.
        for line in re.split(r"[\n\.•]", safe):
            line = _clean(line)
            if 8 <= len(line) <= 160 and _VALUE_HINTS.search(line):
                if line not in values:
                    values.append(line)
        # Recent updates: dated SENTENCES only (never undated "news").
        for line in re.split(r"(?<=[.!?])\s+|[\n•]", safe):
            line = _clean(line)
            if _DATE_RE.search(line) and 8 <= len(line) <= 240 and line not in recent:
                recent.append(line)

    jd_safe = None
    if job_description:
        jd_safe = _scan_ok(job_description, "Company job description", notes)

    if not description and not sources:
        notes.append("No company material provided — add an official URL or upload documents.")
    if not recent:
        notes.append("No dated official updates found; no recent news is inferred.")

    return CompanyContext(
        company_name=company_name.strip(),
        official_website=official, career_page=careers, industry=industry,
        company_description=description,
        products_services=products, values=values[:20], recent_official_updates=recent[:20],
        annual_report_sources=annual, investor_relations_sources=investor,
        provided_job_description=jd_safe, source_references=sources,
        retrieved_at=retrieved_at, notes=notes,
    )
