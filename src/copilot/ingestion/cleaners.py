"""Conservative text cleaning for ingested documents.

Cleaning is deliberately minimal — it normalises whitespace and collapses
excess blank lines but never rewrites wording, headings or meaningful
punctuation. Source content must reach retrieval essentially intact.
"""

from __future__ import annotations

import re

__all__ = ["clean_text"]

# Zero-width and non-breaking oddities that leak in from PDFs/web copy.
_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍﻿"), None)
_TRAILING_WS = re.compile(r"[ \t]+(\n)")
_MANY_SPACES = re.compile(r"[ \t]{2,}")
_MANY_BLANK_LINES = re.compile(r"\n{3,}")


def clean_text(text: str) -> str:
    """Normalise whitespace conservatively; preserve structure and punctuation.

    - Normalise newlines and strip zero-width characters and non-breaking spaces.
    - Trim trailing spaces on each line; collapse runs of spaces/tabs to one.
    - Collapse 3+ consecutive blank lines to a single blank line.
    - Headings, lists and punctuation are left untouched.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.translate(_ZERO_WIDTH).replace(" ", " ")
    text = _TRAILING_WS.sub(r"\1", text)
    text = _MANY_SPACES.sub(" ", text)
    text = _MANY_BLANK_LINES.sub("\n\n", text)
    return text.strip()
