"""Validation of the Phase 8 taxonomy extension.

Phase 8's required interface introduced interview types and interviewer
personas that had no honest mapping to the existing domain vocabulary, so the
shared taxonomy in ``src/constants.py`` (and the persona tones in
``src/prompts.py``) was extended. These tests lock in that the extension is
additive, distinct, validated, prompt-mapped and backward compatible.
"""

import pytest

from src import constants, prompts, ui_helpers
from src.models import InterviewConfiguration

# The new concepts and their stable internal ids.
NEW_INTERVIEW_TYPES = ["leadership", "culture_values", "stakeholder", "executive_board"]
NEW_PERSONAS = ["sceptical_executive", "fast_paced_panel"]

# The full set that existed before Phase 8 — must all still be present/valid.
ORIGINAL_INTERVIEW_TYPES = [
    "screening",
    "behavioural",
    "technical",
    "situational",
    "competency",
    "case_study",
    "portfolio",
    "panel",
]
ORIGINAL_PERSONAS = ["supportive", "neutral", "formal", "challenging"]


def _config(
    interview_types: list[str], persona: str = "neutral"
) -> InterviewConfiguration:
    return InterviewConfiguration(
        target_role="Registered Nurse",
        industry_or_sector="healthcare",
        career_level="senior",
        interview_types=interview_types,
        interviewer_persona=persona,
        difficulty="moderate",
        response_detail="standard",
    )


# --- 1 & 2. Distinct stable ids; nothing renamed/removed --------------------


class TestStableIds:
    def test_interview_type_ids_are_unique(self) -> None:
        assert len(set(constants.INTERVIEW_TYPES)) == len(constants.INTERVIEW_TYPES)

    def test_persona_ids_are_unique(self) -> None:
        assert len(set(constants.INTERVIEWER_PERSONAS)) == len(
            constants.INTERVIEWER_PERSONAS
        )

    def test_new_ids_present_and_distinct_from_existing(self) -> None:
        for new_id in NEW_INTERVIEW_TYPES:
            assert new_id in constants.INTERVIEW_TYPES
            assert new_id not in ORIGINAL_INTERVIEW_TYPES
        for new_id in NEW_PERSONAS:
            assert new_id in constants.INTERVIEWER_PERSONAS
            assert new_id not in ORIGINAL_PERSONAS

    def test_no_existing_id_was_removed_or_renamed(self) -> None:
        # Every original id survives, in its original position (append-only).
        assert list(constants.INTERVIEW_TYPES[: len(ORIGINAL_INTERVIEW_TYPES)]) == (
            ORIGINAL_INTERVIEW_TYPES
        )
        assert list(constants.INTERVIEWER_PERSONAS[: len(ORIGINAL_PERSONAS)]) == (
            ORIGINAL_PERSONAS
        )


# --- 3. UI labels separated from internal values ----------------------------


class TestLabelsSeparatedFromValues:
    def test_labels_differ_from_ids(self) -> None:
        for label, domain_id in ui_helpers.INTERVIEW_TYPES + ui_helpers.PERSONAS:
            assert label != domain_id

    def test_new_concepts_have_human_labels_mapping_to_new_ids(self) -> None:
        type_map = dict(ui_helpers.INTERVIEW_TYPES)
        assert type_map["Leadership"] == "leadership"
        assert type_map["Culture and values"] == "culture_values"
        assert type_map["Stakeholder or client"] == "stakeholder"
        assert type_map["Executive or board"] == "executive_board"
        persona_map = dict(ui_helpers.PERSONAS)
        assert persona_map["Sceptical executive"] == "sceptical_executive"
        assert persona_map["Fast-paced panel"] == "fast_paced_panel"

    def test_every_ui_id_is_a_valid_domain_id(self) -> None:
        for _, domain_id in ui_helpers.INTERVIEW_TYPES:
            assert domain_id in constants.INTERVIEW_TYPES
        for _, domain_id in ui_helpers.PERSONAS:
            assert domain_id in constants.INTERVIEWER_PERSONAS


# --- 4. Model validation accepts each new value -----------------------------


class TestModelValidation:
    @pytest.mark.parametrize("interview_type", NEW_INTERVIEW_TYPES)
    def test_new_interview_type_accepted(self, interview_type: str) -> None:
        config = _config([interview_type])
        assert config.interview_types == [interview_type]

    @pytest.mark.parametrize("persona", NEW_PERSONAS)
    def test_new_persona_accepted(self, persona: str) -> None:
        config = _config(["behavioural"], persona)
        assert config.interviewer_persona == persona

    def test_new_values_combine_together(self) -> None:
        config = _config(NEW_INTERVIEW_TYPES, "sceptical_executive")
        assert config.interview_types == NEW_INTERVIEW_TYPES
        assert config.interviewer_persona == "sceptical_executive"


# --- 5. Prompt generation for each new interview type -----------------------


class TestPromptMapping:
    @pytest.mark.parametrize("interview_type", NEW_INTERVIEW_TYPES)
    def test_interview_type_appears_in_system_prompt(
        self, interview_type: str
    ) -> None:
        prompt = prompts.build_system_prompt("zero_shot", _config([interview_type]))
        assert interview_type in prompt

    @pytest.mark.parametrize("interview_type", NEW_INTERVIEW_TYPES)
    def test_interview_type_used_across_task_api(self, interview_type: str) -> None:
        messages = prompts.build_task_messages(
            prompts.TASK_QUESTION, "role_persona", _config([interview_type])
        )
        assert interview_type in messages[0]["content"]


# --- 6. Persona tones are present, distinct and on-spec ----------------------


class TestPersonaTones:
    def test_new_personas_have_explicit_tone_entries(self) -> None:
        # No silent fallback to the generic "professional".
        for persona in NEW_PERSONAS:
            assert persona in prompts._PERSONA_TONE

    def test_tones_are_materially_distinct(self) -> None:
        tones = prompts._PERSONA_TONE
        assert tones["sceptical_executive"] != tones["fast_paced_panel"]

    def test_sceptical_executive_challenges_claims_and_requests_evidence(self) -> None:
        prompt = prompts.build_system_prompt(
            "zero_shot", _config(["behavioural"], "sceptical_executive")
        )
        assert "challenge unsupported claims" in prompt
        assert "evidence" in prompt

    def test_fast_paced_panel_multiple_perspectives_concise_and_fast(self) -> None:
        prompt = prompts.build_system_prompt(
            "zero_shot", _config(["behavioural"], "fast_paced_panel")
        )
        assert "multiple interviewer viewpoints" in prompt
        assert "concise" in prompt
        assert "quick transitions" in prompt


# --- 7. Round-trip serialization --------------------------------------------


class TestRoundTripSerialization:
    def test_config_with_new_values_round_trips(self) -> None:
        original = _config(NEW_INTERVIEW_TYPES, "fast_paced_panel")
        restored = InterviewConfiguration.model_validate_json(
            original.model_dump_json()
        )
        assert restored == original
        assert restored.interview_types == NEW_INTERVIEW_TYPES
        assert restored.interviewer_persona == "fast_paced_panel"


# --- 8. Backward compatibility with all existing values ----------------------


class TestBackwardCompatibility:
    def test_all_original_interview_types_still_valid(self) -> None:
        config = _config(ORIGINAL_INTERVIEW_TYPES)
        assert config.interview_types == ORIGINAL_INTERVIEW_TYPES

    @pytest.mark.parametrize("persona", ORIGINAL_PERSONAS)
    def test_all_original_personas_still_valid(self, persona: str) -> None:
        assert _config(["behavioural"], persona).interviewer_persona == persona

    def test_invalid_values_still_rejected(self) -> None:
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            _config(["telepathy"])
        with pytest.raises(ValidationError):
            _config(["behavioural"], "mind_reader")
