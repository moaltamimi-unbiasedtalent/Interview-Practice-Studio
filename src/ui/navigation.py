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

__all__ = [
    "APP_TITLE",
    "APP_TAGLINE",
    "NAV_ITEMS",
    "CAREER_ROUTES",
    "HOME",
    "CAREER",
    "INTERVIEW",
    "KNOWLEDGE_BASE",
    "RAG_INSPECTOR",
    "EVALUATION",
]
