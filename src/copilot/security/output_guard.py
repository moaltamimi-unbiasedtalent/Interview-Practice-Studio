"""Output-side guard: redact secret-like strings, flag leakage & bad citations.

Defence in depth. We never place secrets in prompts, but the final answer is
still scanned for accidental secret-like strings (redacted), for verbatim
system-instruction leakage (flagged), and for citation markers that do not map to
a real retrieved source (flagged).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

__all__ = ["OutputGuardResult", "guard_output"]

# (label, pattern) for secret-like strings.
_SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("openrouter_key", re.compile(r"sk-or-[A-Za-z0-9\-]{8,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]{16,}")),
    (
        "assigned_secret",
        re.compile(r"(?i)\b(api[_-]?key|secret|password|access[_-]?token)\b\s*[:=]\s*\S{6,}"),
    ),
]

# Verbatim fragments of our own system instructions that must never surface.
_LEAK_MARKERS = [
    "you are the career intelligence copilot",
    "grounding rules",
    "treat [retrieved evidence]",
    "[tool results] are trusted values",
    "query-understanding stage",
]

_CITATION_RE = re.compile(r"\[\d+\]")


@dataclass
class OutputGuardResult:
    safe_answer: str
    redacted_secrets: int = 0
    leaked_system: bool = False
    invalid_citations: list[str] = field(default_factory=list)
    findings: list[str] = field(default_factory=list)

    @property
    def safe(self) -> bool:
        return not self.findings


def guard_output(answer: str, allowed_markers: set[str] | None = None) -> OutputGuardResult:
    """Redact secret-like strings and flag leakage / invalid citations."""
    safe = answer or ""
    findings: list[str] = []
    redacted = 0

    for label, pattern in _SECRET_PATTERNS:
        safe, count = pattern.subn("[REDACTED]", safe)
        if count:
            redacted += count
            findings.append(f"Redacted {count} secret-like string(s) ({label}).")

    lowered = safe.lower()
    leaked = any(marker in lowered for marker in _LEAK_MARKERS)
    if leaked:
        findings.append("Possible system-instruction leakage detected.")

    invalid: list[str] = []
    if allowed_markers is not None:
        for marker in sorted(set(_CITATION_RE.findall(safe))):
            if marker not in allowed_markers:
                invalid.append(marker)
        if invalid:
            findings.append(f"Removed invalid citation reference(s): {invalid}.")
            # Strip unsupported markers from the user-visible answer so a citation
            # never points at evidence that does not exist. Valid markers are left
            # exactly as written (no renumbering — that would break the mapping).
            invalid_set = set(invalid)

            def _strip(match: "re.Match") -> str:
                return "" if match.group(0) in invalid_set else match.group(0)

            safe = _CITATION_RE.sub(_strip, safe)
            # Tidy any double spaces / space-before-punctuation left behind.
            safe = re.sub(r"[ \t]{2,}", " ", safe)
            safe = re.sub(r"\s+([.,;:!?])", r"\1", safe)

    return OutputGuardResult(
        safe_answer=safe,
        redacted_secrets=redacted,
        leaked_system=leaked,
        invalid_citations=invalid,
        findings=findings,
    )
