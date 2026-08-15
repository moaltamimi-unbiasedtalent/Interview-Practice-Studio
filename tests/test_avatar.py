"""Tests for the interviewer avatar presentation (AvatarRenderer)."""

import pytest

from src import constants
from src.avatar import AvatarRenderer, LocalAvatarRenderer, persona_presentation


def _render(persona="neutral", state=constants.AVATAR_IDLE) -> str:
    return LocalAvatarRenderer().render(persona=persona, state=state)


class TestPersonaPresentation:
    def test_known_persona(self) -> None:
        pres = persona_presentation("supportive")
        assert pres["label"] == "Friendly recruiter"
        assert pres["accent"].startswith("#")

    def test_unknown_persona_falls_back(self) -> None:
        assert persona_presentation("nope") == constants.DEFAULT_PERSONA_PRESENTATION
        assert persona_presentation(None) == constants.DEFAULT_PERSONA_PRESENTATION


class TestLocalAvatarRenderer:
    def test_returns_html_with_accessible_label(self) -> None:
        html = _render(persona="formal", state=constants.AVATAR_SPEAKING)
        assert 'role="img"' in html
        assert "aria-label=" in html
        assert "Formal interviewer" in html
        assert "Speaking" in html

    def test_reduced_motion_is_respected(self) -> None:
        assert "prefers-reduced-motion" in _render(state=constants.AVATAR_SPEAKING)

    def test_speaking_state_animates_ring(self) -> None:
        assert 'class="ipa-ring ipa-speaking"' in _render(
            state=constants.AVATAR_SPEAKING
        )

    def test_listening_state_animates_ring(self) -> None:
        assert 'class="ipa-ring ipa-listening"' in _render(
            state=constants.AVATAR_LISTENING
        )

    def test_idle_state_is_static(self) -> None:
        html = _render(state=constants.AVATAR_IDLE)
        assert 'class="ipa-ring"' in html
        assert "ipa-speaking" not in html.split("<div class=")[-1]  # not on the ring

    def test_thinking_shows_dots(self) -> None:
        assert "ipa-dots" in _render(state=constants.AVATAR_THINKING)

    def test_unknown_state_falls_back_to_ready(self) -> None:
        html = _render(state="bogus")
        assert "Ready" in html

    def test_personas_have_distinct_accents(self) -> None:
        supportive = _render(persona="supportive")
        executive = _render(persona="sceptical_executive")
        assert supportive != executive  # different accent styling


def test_avatar_renderer_is_abstract() -> None:
    with pytest.raises(TypeError):
        AvatarRenderer()  # type: ignore[abstract]
