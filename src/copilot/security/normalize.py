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

from src.core.security.normalize import ZERO_WIDTH as _ZERO_WIDTH
from src.core.security.normalize import count_control_chars, strip_control

__all__ = ["normalize_for_storage", "normalize_for_detection", "count_control_chars"]

# Low-level primitives (zero-width table, control stripping, control-char count)
# are shared from src.core.security; the domain-specific normalisation below is
# kept here because the Career injection scanner depends on its exact behaviour.
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_PUNCT_RE = re.compile(r"[^a-z0-9\s]")


def normalize_for_storage(text: str) -> str:
    """Light clean: strip zero-width + control chars, keep case/punctuation."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.translate(_ZERO_WIDTH)
    text = strip_control(text)
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
