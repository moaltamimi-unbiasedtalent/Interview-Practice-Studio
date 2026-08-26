"""Reusable, domain-agnostic security primitives.

Only *generic* normalisation/validation lives here (control/zero-width stripping,
NFKC, control-char counting). Domain-specific security — the Career injection
scanner and guards, the Interview input/injection guard — stays in
``src/copilot/security`` and ``src/security.py`` respectively, because their
behaviour differs.
"""

from src.core.security.normalize import (
    ZERO_WIDTH,
    control_char_regex,
    count_control_chars,
    strip_control,
    strip_zero_width,
)

__all__ = [
    "ZERO_WIDTH",
    "control_char_regex",
    "count_control_chars",
    "strip_control",
    "strip_zero_width",
]
