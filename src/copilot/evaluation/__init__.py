"""Evaluation utilities for Career Intelligence Copilot.

Phase 5 adds a lightweight retrieval comparison baseline (vector vs keyword vs
hybrid). A fuller RAG evaluation (an optional hard task) comes later.
"""

from src.copilot.evaluation.retrieval_eval import (
    ModeMetrics,
    RetrievalProbe,
    evaluate_modes,
    load_probes,
)

__all__ = ["ModeMetrics", "RetrievalProbe", "evaluate_modes", "load_probes"]
