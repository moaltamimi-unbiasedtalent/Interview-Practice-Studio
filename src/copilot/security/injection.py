"""Deterministic, explainable prompt-injection scanner.

Normalise the text, match a fixed set of weighted indicators, sum the weights and
map to a verdict: ``allow`` / ``allow_with_warning`` / ``block``. The rules are
transparent and auditable — and deliberately *best effort*: this catches obvious
attacks, not every possible one (see ``docs/security.md``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.copilot import constants
from src.copilot.security.normalize import normalize_for_detection

__all__ = ["InjectionScan", "scan_text", "INDICATORS"]

# (label, weight, compiled pattern). High weight (3.0) = a single hit blocks;
# medium (2.0) = a single hit warns, two combine to a block.
_RAW_INDICATORS: list[tuple[str, float, str]] = [
    (
        "ignore_previous_instructions",
        3.0,
        r"\b(ignore|disregard|forget|override)\b.{0,25}\b(previous|prior|above|earlier|all|the)\b.{0,25}\b(instruction|instructions|prompt|prompts|rule|rules|context|message|messages)\b",
    ),
    (
        "reveal_system_prompt",
        3.0,
        r"\b(reveal|show|print|repeat|display|output|give|tell)\b.{0,25}\b(system|initial|hidden|developer|original)\b.{0,15}\b(prompt|prompts|message|messages|instruction|instructions)\b",
    ),
    (
        "reveal_secret",
        3.0,
        r"\b(reveal|show|print|leak|give|tell|expose|send|what is|whats)\b.{0,25}\b(api key|apikey|secret|secrets|password|passwords|token|tokens|credential|credentials|environment variable|env var)\b",
    ),
    (
        "disable_security",
        3.0,
        r"\b(disable|turn off|bypass|remove|deactivate|switch off|ignore)\b.{0,25}\b(security|safety|guardrail|guardrails|filter|filters|moderation|restriction|restrictions|protection|rules)\b",
    ),
    (
        "execute_commands",
        3.0,
        r"\b(execute|run|eval|exec|invoke)\b.{0,20}\b(command|commands|shell|code|python|script|os system|subprocess|bash|sql)\b",
    ),
    (
        "follow_source_instructions",
        3.0,
        r"\b(follow|obey|execute|comply with|do what|act on)\b.{0,25}\b(instruction|instructions|command|commands|direction|directions)\b.{0,20}\b(in|from|within|inside|below|this|the)\b.{0,20}\b(document|source|sources|context|text|passage|chunk|article|resume|cv|job description|posting)\b",
    ),
    (
        "role_change",
        2.0,
        r"\b(you are now|act as|pretend to be|from now on you are|new role|assume the role of|roleplay as|behave as)\b",
    ),
    (
        "jailbreak_mode",
        2.0,
        r"\b(do anything now|dan mode|jailbreak|developer mode enabled|unfiltered mode)\b",
    ),
    (
        "new_instructions",
        2.0,
        r"\b(new instructions|updated instructions|the real instructions|here are your instructions|system override|admin override)\b",
    ),
    (
        "print_everything_above",
        2.0,
        r"\b(repeat|print|show|output)\b.{0,15}\b(everything above|the text above|your instructions|your prompt|this conversation)\b",
    ),
]

INDICATORS: list[tuple[str, float, re.Pattern]] = [
    (label, weight, re.compile(pattern)) for label, weight, pattern in _RAW_INDICATORS
]

# Substring indicators checked against the whitespace-removed text, to catch
# heavy obfuscation (e.g. "i g n o r e   a l l   p r e v i o u s ...").
_COLLAPSED_INDICATORS: list[tuple[str, float, tuple[str, ...]]] = [
    ("ignore_previous_collapsed", 3.0, ("ignoreallprevious", "ignorepreviousinstruction", "ignoreallinstruction", "disregardprevious", "disregardallprevious")),
    ("reveal_prompt_collapsed", 3.0, ("revealsystemprompt", "showsystemprompt", "printsystemprompt", "outputsystemprompt", "repeatsystemprompt")),
    ("reveal_secret_collapsed", 3.0, ("revealapikey", "showapikey", "leakapikey", "revealsecret", "revealpassword", "printapikey")),
    ("disable_security_collapsed", 3.0, ("disablesecurity", "disablesafety", "bypasssecurity", "disableguardrails", "turnoffsafety")),
]


@dataclass
class InjectionScan:
    """The result of scanning one piece of text for injection."""

    verdict: str = constants.VERDICT_ALLOW
    score: float = 0.0
    indicators: list[str] = field(default_factory=list)

    @property
    def blocked(self) -> bool:
        return self.verdict == constants.VERDICT_BLOCK

    @property
    def flagged(self) -> bool:
        return self.verdict != constants.VERDICT_ALLOW


def scan_text(text: str) -> InjectionScan:
    """Scan ``text`` and return a verdict with matched indicators and score."""
    if not text or not text.strip():
        return InjectionScan()
    normalized = normalize_for_detection(text)
    matched: list[str] = []
    score = 0.0
    for label, weight, pattern in INDICATORS:
        if pattern.search(normalized):
            matched.append(label)
            score += weight

    collapsed = normalized.replace(" ", "")
    for label, weight, needles in _COLLAPSED_INDICATORS:
        if label in matched:
            continue  # already counted by the regex pass
        if any(needle in collapsed for needle in needles):
            matched.append(label)
            score += weight

    if score >= constants.INJECTION_BLOCK_THRESHOLD:
        verdict = constants.VERDICT_BLOCK
    elif score >= constants.INJECTION_WARN_THRESHOLD:
        verdict = constants.VERDICT_WARN
    else:
        verdict = constants.VERDICT_ALLOW
    return InjectionScan(verdict=verdict, score=score, indicators=matched)
