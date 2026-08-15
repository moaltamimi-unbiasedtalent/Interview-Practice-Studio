"""Virtual interviewer presentation (the AI interviewer avatar).

A small abstraction so the candidate-facing interviewer can later be replaced by
a realtime digital-human provider without touching any interview-domain logic.
The default :class:`LocalAvatarRenderer` is local, inexpensive and dependency-
free: it returns a self-contained, accessible, theme-neutral SVG/HTML snippet for
a persona and a state.

Design notes:
* Professional and neutral — no caricatures. A generic bust silhouette in a
  persona-accented ring, not a likeness of any person.
* Tasteful state animation only (speaking pulse, thinking dots). No fake
  phoneme-accurate lip-sync.
* Accessible: ``role="img"`` with a descriptive ``aria-label``; animation is
  disabled under ``prefers-reduced-motion``.
"""

from __future__ import annotations

import html
from abc import ABC, abstractmethod

from src import constants

__all__ = ["AvatarRenderer", "LocalAvatarRenderer", "persona_presentation"]


def persona_presentation(persona: str | None) -> dict[str, str]:
    """Return the friendly label + accent colour for an interviewer persona."""
    return constants.INTERVIEWER_PERSONA_PRESENTATION.get(
        persona or "", constants.DEFAULT_PERSONA_PRESENTATION
    )


def _state_caption(state: str) -> str:
    return {
        constants.AVATAR_SPEAKING: "Speaking",
        constants.AVATAR_LISTENING: "Listening",
        constants.AVATAR_THINKING: "Thinking…",
        constants.AVATAR_IDLE: "Ready",
    }.get(state, "Ready")


class AvatarRenderer(ABC):
    """Renders the interviewer avatar for a persona + state.

    Implementations return an HTML fragment suitable for embedding (e.g. via
    ``streamlit.components.v1.html``). A future realtime digital-human provider
    can implement this interface without changing interview logic.
    """

    name: str = "avatar"

    @abstractmethod
    def render(self, *, persona: str | None, state: str, height: int = 220) -> str:
        """Return an HTML fragment presenting the interviewer."""


class LocalAvatarRenderer(AvatarRenderer):
    """Default, local, inexpensive avatar — a neutral styled silhouette."""

    name = "local"

    def render(self, *, persona: str | None, state: str, height: int = 220) -> str:
        if state not in constants.AVATAR_STATES:
            state = constants.AVATAR_IDLE
        presentation = persona_presentation(persona)
        accent = presentation["accent"]
        label = presentation["label"]
        caption = _state_caption(state)
        aria = html.escape(f"AI interviewer, {label}, {caption}")
        speaking = state == constants.AVATAR_SPEAKING
        listening = state == constants.AVATAR_LISTENING
        thinking = state == constants.AVATAR_THINKING

        # Thinking dots only shown when thinking; speaking ring pulses; listening
        # shows a gentle steady ring. All animation is disabled for reduced motion.
        dots = (
            '<div class="ipa-dots" aria-hidden="true"><span></span><span></span>'
            "<span></span></div>"
            if thinking
            else ""
        )
        ring_class = "ipa-ring"
        if speaking:
            ring_class += " ipa-speaking"
        elif listening:
            ring_class += " ipa-listening"

        return f"""
<div class="ipa-avatar" role="img" aria-label="{aria}">
  <style>
    .ipa-avatar {{
      display:flex; flex-direction:column; align-items:center; gap:.5rem;
      font-family: system-ui, sans-serif; color:#5f6368;
    }}
    .ipa-ring {{
      width:120px; height:120px; border-radius:50%;
      display:flex; align-items:center; justify-content:center;
      background:#f1f3f4; border:4px solid {accent};
      box-shadow:0 0 0 0 {accent}55;
    }}
    .ipa-speaking {{ animation: ipa-pulse 1.1s ease-in-out infinite; }}
    .ipa-listening {{ animation: ipa-breathe 2.6s ease-in-out infinite; }}
    @keyframes ipa-pulse {{
      0%   {{ box-shadow:0 0 0 0 {accent}55; }}
      70%  {{ box-shadow:0 0 0 16px {accent}00; }}
      100% {{ box-shadow:0 0 0 0 {accent}00; }}
    }}
    @keyframes ipa-breathe {{
      0%,100% {{ transform:scale(1); }} 50% {{ transform:scale(1.03); }}
    }}
    .ipa-label {{ font-weight:600; color:#3c4043; }}
    .ipa-state {{ font-size:.85rem; }}
    .ipa-dots span {{
      display:inline-block; width:6px; height:6px; margin:0 2px; border-radius:50%;
      background:{accent}; animation: ipa-blink 1.2s infinite both;
    }}
    .ipa-dots span:nth-child(2) {{ animation-delay:.2s; }}
    .ipa-dots span:nth-child(3) {{ animation-delay:.4s; }}
    @keyframes ipa-blink {{ 0%,80%,100% {{ opacity:.2; }} 40% {{ opacity:1; }} }}
    @media (prefers-reduced-motion: reduce) {{
      .ipa-speaking, .ipa-listening, .ipa-dots span {{ animation:none !important; }}
    }}
  </style>
  <div class="{ring_class}">
    <svg width="72" height="72" viewBox="0 0 24 24" aria-hidden="true"
         fill="{accent}">
      <circle cx="12" cy="8" r="4"/>
      <path d="M4 20c0-4 3.6-6 8-6s8 2 8 6v1H4z"/>
    </svg>
  </div>
  <div class="ipa-label">{html.escape(label)}</div>
  <div class="ipa-state">{html.escape(caption)}</div>
  {dots}
</div>
""".strip()
