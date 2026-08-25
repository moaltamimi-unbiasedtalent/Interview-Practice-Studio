"""Deterministic, explainable text matching for the gap analyzer.

No LLM, no randomness: requirements and candidate text are tokenised, lightly
stemmed, and compared by token coverage. The rules are simple on purpose so a
match decision can be explained in a project review.
"""

from __future__ import annotations

import re

__all__ = ["tokenize", "stem", "significant_tokens", "coverage"]

_TOKEN_RE = re.compile(r"[a-z0-9+#]+")

# Very common words carry no matching signal; drop them.
_STOPWORDS = frozenset(
    """
    a an the and or of to for in on with without within into from by as at is are be being been
    this that these those you your our their his her its it we they i my me
    strong excellent good ability able experience experienced skills skill knowledge
    proven demonstrated understanding using use used work working across including etc
    """.split()
)

# Light suffix stemming so "managing"/"managed"/"management" align on "manag".
_SUFFIXES = ("ations", "ation", "ities", "ility", "ments", "ment", "ing", "ers", "er", "ed", "es", "s")


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall((text or "").lower())


def stem(token: str) -> str:
    for suffix in _SUFFIXES:
        if len(token) > len(suffix) + 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def significant_tokens(text: str) -> set[str]:
    """Stemmed, stop-word-filtered token set for matching."""
    return {stem(tok) for tok in tokenize(text) if tok not in _STOPWORDS and len(tok) > 1}


def coverage(requirement: str, candidate_tokens: set[str]) -> float:
    """Fraction of a requirement's significant tokens present in the candidate.

    Returns a value in [0, 1]. A requirement with no significant tokens returns
    0.0 (it cannot be evidenced).
    """
    req_tokens = significant_tokens(requirement)
    if not req_tokens:
        return 0.0
    present = sum(1 for tok in req_tokens if tok in candidate_tokens)
    return present / len(req_tokens)
