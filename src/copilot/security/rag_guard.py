"""Treat retrieved chunks as untrusted source material.

Retrieved text is data, never instructions. Each chunk is scanned for embedded
injection: a blocked chunk (imperative attack text) is **excluded** from the
evidence; a warned chunk is kept but marked. If enough valid evidence remains the
pipeline continues on the safe subset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.copilot.models import RetrievalResult
from src.copilot.security.injection import InjectionScan, scan_text

__all__ = ["ScreenResult", "screen_results"]


@dataclass
class ScreenResult:
    """Outcome of screening retrieved results for injection."""

    kept: list[RetrievalResult] = field(default_factory=list)
    excluded: list[tuple[RetrievalResult, InjectionScan]] = field(default_factory=list)
    warned: list[tuple[RetrievalResult, InjectionScan]] = field(default_factory=list)

    @property
    def excluded_count(self) -> int:
        return len(self.excluded)

    def summary(self) -> str | None:
        if not self.excluded and not self.warned:
            return None
        parts = []
        if self.excluded:
            parts.append(f"excluded {len(self.excluded)} chunk(s) with embedded instructions")
        if self.warned:
            parts.append(f"flagged {len(self.warned)} suspicious chunk(s)")
        return "Retrieved-content guard: " + ", ".join(parts) + "."


def screen_results(results: list[RetrievalResult]) -> ScreenResult:
    """Exclude retrieved chunks whose text is an injection attack; mark warnings."""
    screen = ScreenResult()
    for result in results:
        scan = scan_text(result.chunk.text)
        if scan.blocked:
            screen.excluded.append((result, scan))
            continue  # drop injected evidence
        if scan.flagged:
            screen.warned.append((result, scan))
        screen.kept.append(result)
    return screen
