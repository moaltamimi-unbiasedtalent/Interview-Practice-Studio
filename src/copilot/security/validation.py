"""Explicit input validation with normalisation and non-silent limits.

Applies per-field character limits and neutralises control/obfuscation
characters. Over-limit input is bounded and **flagged** (``truncated`` + a note)
rather than silently dropped, so the caller always knows content was cut.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.copilot import constants
from src.copilot.security.normalize import count_control_chars, normalize_for_storage

__all__ = ["ValidationResult", "validate_input", "LIMITS"]

LIMITS: dict[str, int] = {
    "query": constants.MAX_QUERY_CHARS,
    "job_description": constants.MAX_JOB_DESCRIPTION_CHARS,
    "candidate_background": constants.MAX_CANDIDATE_BACKGROUND_CHARS,
    "upload": constants.MAX_UPLOAD_CHARS,
}


@dataclass
class ValidationResult:
    ok: bool
    cleaned: str
    kind: str
    truncated: bool = False
    control_chars_removed: int = 0
    notes: list[str] = field(default_factory=list)
    error: str | None = None


def validate_input(
    text: str, kind: str = "query", *, truncate: bool = True
) -> ValidationResult:
    """Validate and normalise ``text`` for the given field ``kind``."""
    raw = text or ""
    control = count_control_chars(raw)
    cleaned = normalize_for_storage(raw)
    limit = LIMITS.get(kind, constants.MAX_QUERY_CHARS)
    notes: list[str] = []
    truncated = False
    error: str | None = None
    ok = True

    if control:
        notes.append(f"Removed {control} control/zero-width character(s).")

    if not cleaned.strip():
        return ValidationResult(
            ok=False,
            cleaned="",
            kind=kind,
            control_chars_removed=control,
            notes=notes,
            error="Input is empty after cleaning.",
        )

    if len(cleaned) > limit:
        if truncate:
            cleaned = cleaned[:limit]
            truncated = True
            notes.append(
                f"Input exceeded the {limit}-character limit for {kind} and was "
                "truncated (flagged, not silent)."
            )
        else:
            ok = False
            error = f"Input exceeds the {limit}-character limit for {kind}."

    return ValidationResult(
        ok=ok,
        cleaned=cleaned,
        kind=kind,
        truncated=truncated,
        control_chars_removed=control,
        notes=notes,
        error=error,
    )
