"""Prompt-injection and RAG security for Career Intelligence Copilot.

Deterministic, explainable, best-effort defences (not a guarantee):

* :mod:`normalize` — neutralise control/obfuscation characters before analysis.
* :mod:`injection` — weighted-indicator injection scanner (allow / warn / block).
* :mod:`validation` — explicit input limits, no silent truncation of content.
* :mod:`rag_guard` — treat retrieved chunks as untrusted; flag/exclude injected ones.
* :mod:`output_guard` — redact secret-like strings and drop invalid citations.

See ``docs/security.md`` for the threat model, trust boundaries and limitations.
"""

from src.copilot.security.injection import InjectionScan, scan_text
from src.copilot.security.output_guard import OutputGuardResult, guard_output
from src.copilot.security.rag_guard import screen_results
from src.copilot.security.validation import ValidationResult, validate_input

__all__ = [
    "InjectionScan",
    "scan_text",
    "ValidationResult",
    "validate_input",
    "screen_results",
    "OutputGuardResult",
    "guard_output",
]
