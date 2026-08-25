"""Text normalisation used before injection analysis.

Attackers hide instructions with zero-width characters, control characters and
odd spacing. Normalisation removes that obfuscation so the scanner sees the plain
intent. Two functions:

* :func:`normalize_for_storage` — a light clean kept for display/use (preserves
  case and punctuation).
* :func:`normalize_for_detection` — an aggressive lower-cased form for matching
  (strips zero-width chars, collapses spacing, drops most punctuation).
"""

from __future__ import annotations

import re
import unicodedata

__all__ = ["normalize_for_storage", "normalize_for_detection", "count_control_chars"]

# Zero-width / bidi / BOM characters commonly used to obfuscate.
_ZERO_WIDTH = dict.fromkeys(
    [
        0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0x2060, 0xFEFF,
        0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
    ],
    None,
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")


def count_control_chars(text: str) -> int:
    """Number of disallowed control/zero-width characters in ``text``."""
    zero_width = sum(1 for ch in text if ord(ch) in _ZERO_WIDTH)
    return len(_CONTROL_RE.findall(text)) + zero_width


def normalize_for_storage(text: str) -> str:
    """Light clean: strip zero-width + control chars, keep case/punctuation."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_ZERO_WIDTH)
    text = _CONTROL_RE.sub("", text)
    text = _MULTISPACE_RE.sub(" ", text)
    return text.strip()


def normalize_for_detection(text: str) -> str:
    """Aggressive form for matching: NFKC, lower-case, de-obfuscate, de-punctuate."""
    text = normalize_for_storage(text).lower()
    # Collapse simple separator obfuscation like "i-g-n-o-r-e" or "i.g.n.o.r.e".
    text = re.sub(r"(?<=\b\w)[\s._\-]+(?=\w\b)", "", text)
    text = _PUNCT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()
