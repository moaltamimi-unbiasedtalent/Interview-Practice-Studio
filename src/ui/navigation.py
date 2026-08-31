"""Top-level navigation for Interview OS Coach.

One Streamlit app, one URL. The routes split into two groups:

* **Primary** product journey (a radio at the top of the sidebar): Home,
  Career Intelligence, Interview Practice, Knowledge Base.
* **Diagnostic** review pages (secondary buttons lower in the sidebar):
  RAG Inspector and Evaluation. These are always accessible — they are NOT
  gated by reviewer mode — but they stay out of the primary product navigation
  so the candidate journey is uncluttered.

The active application page (``ACTIVE_PAGE_KEY``) is tracked separately from the
primary radio value (``PRIMARY_NAV_KEY``) so a diagnostic page can be shown
without the radio forcing the route back to a primary option.
"""

from __future__ import annotations

APP_TITLE = "Interview OS Coach"
APP_TAGLINE = "Understand the opportunity. Prepare intelligently. Practise realistically."

HOME = "Home"
CAREER = "Career Intelligence"
INTERVIEW = "Interview Practice"
KNOWLEDGE_BASE = "Knowledge Base"
RAG_INSPECTOR = "RAG Inspector"
EVALUATION = "Evaluation"

# Primary product journey — the top-of-sidebar radio.
PRIMARY_NAV_ITEMS: list[str] = [
    HOME,
    CAREER,
    INTERVIEW,
    KNOWLEDGE_BASE,
]

# Secondary review / diagnostic pages — always accessible, shown lower down.
DIAGNOSTIC_NAV_ITEMS: list[str] = [
    RAG_INSPECTOR,
    EVALUATION,
]

# The full route list (kept for routing/tests): primary first, diagnostics last.
NAV_ITEMS: list[str] = PRIMARY_NAV_ITEMS + DIAGNOSTIC_NAV_ITEMS

# Routes handled by the Career Intelligence module.
CAREER_ROUTES = {CAREER, KNOWLEDGE_BASE, RAG_INSPECTOR, EVALUATION}

# Session-state keys for the split active-page / primary-radio model.
ACTIVE_PAGE_KEY = "os_active_page"
PRIMARY_NAV_KEY = "os_primary_nav"

# Grouped display labels for the primary radio (underlying page values unchanged).
NAV_DISPLAY: dict[str, str] = {
    HOME: "🏠  Home",
    CAREER: "Prepare · Career Intelligence",
    INTERVIEW: "Practise · Interview Practice",
    KNOWLEDGE_BASE: "Resources · Knowledge Base",
    RAG_INSPECTOR: "🔎 RAG Inspector",
    EVALUATION: "📊 Evaluation",
}

# Compact labels for the secondary diagnostic buttons.
DIAGNOSTIC_LABELS: dict[str, str] = {
    RAG_INSPECTOR: "🔎 RAG Inspector",
    EVALUATION: "📊 Evaluation",
}

# The platform workflow, reinforced in the sidebar and on Home.
WORKFLOW_STEPS = ["UNDERSTAND", "PREPARE", "PRACTISE", "REVIEW", "IMPROVE"]
WORKFLOW = " → ".join(WORKFLOW_STEPS)


def display_label(page: str) -> str:
    return NAV_DISPLAY.get(page, page)


def is_diagnostic(page: str) -> bool:
    return page in DIAGNOSTIC_NAV_ITEMS

__all__ = [
    "APP_TITLE",
    "APP_TAGLINE",
    "NAV_ITEMS",
    "PRIMARY_NAV_ITEMS",
    "DIAGNOSTIC_NAV_ITEMS",
    "NAV_DISPLAY",
    "DIAGNOSTIC_LABELS",
    "CAREER_ROUTES",
    "ACTIVE_PAGE_KEY",
    "PRIMARY_NAV_KEY",
    "WORKFLOW",
    "WORKFLOW_STEPS",
    "display_label",
    "is_diagnostic",
    "HOME",
    "CAREER",
    "INTERVIEW",
    "KNOWLEDGE_BASE",
    "RAG_INSPECTOR",
    "EVALUATION",
]
