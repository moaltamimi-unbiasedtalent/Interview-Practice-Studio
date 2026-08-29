"""Top-level navigation for Interview OS Coach.

A single ordered list of routes for the one Streamlit app. Career routes are
surfaced at the top level (Knowledge Base / RAG Inspector / Evaluation) alongside
the two product entry points, so everything lives under one URL.
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

NAV_ITEMS: list[str] = [
    HOME,
    CAREER,
    INTERVIEW,
    KNOWLEDGE_BASE,
    RAG_INSPECTOR,
    EVALUATION,
]

# Routes handled by the Career Intelligence module.
CAREER_ROUTES = {CAREER, KNOWLEDGE_BASE, RAG_INSPECTOR, EVALUATION}

# Advanced / diagnostic routes intended for reviewers and graders rather than
# candidates. They are hidden from the nav unless reviewer mode is enabled
# (COPILOT_REVIEWER_MODE), keeping the default candidate journey uncluttered.
ADVANCED_ROUTES = {RAG_INSPECTOR, EVALUATION}


def visible_nav_items(reviewer_mode: bool) -> list[str]:
    """Nav items for the current audience.

    Reviewer mode shows every route (including the Advanced diagnostics);
    otherwise the Advanced routes are hidden. ``NAV_ITEMS`` itself is unchanged.
    """
    if reviewer_mode:
        return list(NAV_ITEMS)
    return [item for item in NAV_ITEMS if item not in ADVANCED_ROUTES]

# Grouped display labels (single-select radio keeps its underlying page values,
# so routing/tests are unchanged; the prefix conveys the product grouping:
# Prepare / Practise / Resources / Advanced).
NAV_DISPLAY: dict[str, str] = {
    HOME: "🏠  Home",
    CAREER: "Prepare · Career Intelligence",
    INTERVIEW: "Practise · Interview Practice",
    KNOWLEDGE_BASE: "Resources · Knowledge Base",
    RAG_INSPECTOR: "Advanced · RAG Inspector",
    EVALUATION: "Advanced · Evaluation",
}

# The platform workflow, reinforced in the sidebar and on Home.
WORKFLOW_STEPS = ["UNDERSTAND", "PREPARE", "PRACTISE", "REVIEW", "IMPROVE"]
WORKFLOW = " → ".join(WORKFLOW_STEPS)


def display_label(page: str) -> str:
    return NAV_DISPLAY.get(page, page)

__all__ = [
    "APP_TITLE",
    "APP_TAGLINE",
    "NAV_ITEMS",
    "NAV_DISPLAY",
    "CAREER_ROUTES",
    "ADVANCED_ROUTES",
    "visible_nav_items",
    "WORKFLOW",
    "WORKFLOW_STEPS",
    "display_label",
    "HOME",
    "CAREER",
    "INTERVIEW",
    "KNOWLEDGE_BASE",
    "RAG_INSPECTOR",
    "EVALUATION",
]
