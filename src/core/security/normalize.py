"""Generic text-normalisation primitives shared across modules.

These are the low-level building blocks (the zero-width table, the control-char
regex, and simple strippers). Higher-level, domain-specific normalisation is
built on top of these in each module's own security package.
"""

from __future__ import annotations

import re

__all__ = [
    "ZERO_WIDTH",
    "control_char_regex",
    "count_control_chars",
    "strip_zero_width",
    "strip_control",
]

# Zero-width / bidi / BOM code points commonly used to obfuscate text.
ZERO_WIDTH: dict[int, None] = dict.fromkeys(
    [
        0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF,
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    ],
    None,
)

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def control_char_regex() -> re.Pattern:
    """The compiled control-character pattern (shared)."""
    return _CONTROL_RE


def count_control_chars(text: str) -> int:
    """Number of disallowed control/zero-width characters in ``text``."""
    zero_width = sum(1 for ch in text if ord(ch) in ZERO_WIDTH)
    return len(_CONTROL_RE.findall(text)) + zero_width


def strip_zero_width(text: str) -> str:
    return (text or "").translate(ZERO_WIDTH)


def strip_control(text: str) -> str:
    return _CONTROL_RE.sub("", text or "")
