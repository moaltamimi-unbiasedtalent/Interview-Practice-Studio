"""Tests for the validated domain models and structured-output schemas.

The focus is on the validation guarantees the rest of the app relies on:
whitespace stripping, rejection of empty required fields, enum-like value
checking, score-range boundaries, rejection of unknown fields, and the
cross-field rules on usage records. No live API calls are made anywhere.
"""

import pytest
from pydantic import ValidationError

from src import constants
from src.models import (
    AnswerEvaluation,
    FinalInterviewReport,
    InterviewConfiguration,
    InterviewQuestion,
    InterviewStrategy,
    ModelSettings,
    UsageRecord,
)


# --- Reusable valid payloads (kept minimal and profession-neutral) ----------


def _valid_configuration_kwargs() -> dict:
    return {
        "target_role": "Registered Nurse",
        "industry_or_sector": "healthcare",
        "career_level": "senior",
        "interview_types": ["behavioural", "situational"],
        "interviewer_persona": "neutral",
        "difficulty": "moderate",
        "response_detail": "standard",
    }


def _valid_strategy_kwargs() -> dict:
    section = ["item one"]
    return {
        "role_summary": "A generic role summary.",
        "likely_interview_stages": section,
        "critical_competencies": section,
        "likely_question_themes": section,
        "probable_challenges": section,
        "evidence_to_prepare": section,
        "technical_or_functional_topics": section,
        "behavioural_topics": section,
        "questions_for_interviewer": section,
        "preparation_priorities": section,
    }


def _valid_question_kwargs() -> dict:
    return {
        "question_id": 1,
        "question": "Describe a time you handled conflicting priorities.",
        "question_type": "behavioural",
        "competency": "prioritisation",
        "difficulty": "moderate",
        "interviewer_intent": "See how the candidate structures trade-offs.",
        "expected_answer_elements": ["context", "action", "result"],
    }


def _valid_evaluation_kwargs() -> dict:
    section = ["a point"]
    return {
        "overall_score": 72,
        "relevance": 8,
        "structure": 7,
        "evidence": 6,
        "role_knowledge": 7,
        "problem_solving": 8,
        "communication": 7,
        "credibility": 8,
        "strengths": section,
        "improvement_areas": section,
        "missing_evidence": section,
        "stronger_answer_structure": "Situation, task, action, result.",
        "improved_example_answer": "A concise improved answer.",
        "follow_up_question": "What would you change with hindsight?",
    }


def _valid_report_kwargs() -> dict:
    section = ["a point"]
    return {
        "overall_readiness_score": 68,
        "performance_summary": "Solid overall with clear gaps to close.",
        "strongest_competencies": section,
        "development_priorities": section,
        "recurring_answer_patterns": section,
        "highest_risk_questions": section,
        "evidence_gaps": section,
        "recommended_practice_actions": section,
        "final_interview_checklist": section,
    }


def _valid_usage_kwargs() -> dict:
    return {
        "model": constants.DEFAULT_MODEL,
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
        "reported_cost": None,
        "calculated_cost": 0.0021,
        "cost_source": "calculated",
        "request_duration_seconds": 1.35,
    }


# --- Whitespace stripping ----------------------------------------------------


class TestWhitespaceStripping:
    def test_scalar_string_is_stripped(self) -> None:
        config = InterviewConfiguration(
            **{**_valid_configuration_kwargs(), "target_role": "  Registered Nurse  "}
        )
        assert config.target_role == "Registered Nurse"

    def test_list_items_are_stripped(self) -> None:
        config = InterviewConfiguration(
            **{**_valid_configuration_kwargs(), "interview_types": ["  behavioural  "]}
        )
        assert config.interview_types == ["behavioural"]

    def test_strategy_list_items_are_stripped(self) -> None:
        strategy = InterviewStrategy(
            **{**_valid_strategy_kwargs(), "critical_competencies": ["  teamwork  "]}
        )
        assert strategy.critical_competencies == ["teamwork"]


# --- Empty / required-field rejection ---------------------------------------


class TestEmptyRejection:
    def test_empty_required_string_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InterviewConfiguration(
                **{**_valid_configuration_kwargs(), "target_role": "   "}
            )

    def test_missing_required_field_is_rejected(self) -> None:
        kwargs = _valid_configuration_kwargs()
        del kwargs["career_level"]
        with pytest.raises(ValidationError):
            InterviewConfiguration(**kwargs)

    def test_empty_list_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InterviewConfiguration(
                **{**_valid_configuration_kwargs(), "interview_types": []}
            )

    def test_list_with_blank_item_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InterviewStrategy(
                **{**_valid_strategy_kwargs(), "critical_competencies": ["ok", "   "]}
            )

    def test_optional_context_defaults_to_empty_string(self) -> None:
        config = InterviewConfiguration(**_valid_configuration_kwargs())
        assert config.company_context == ""
        assert config.job_description == ""
        assert config.candidate_background == ""


# --- Enum-like value validation ---------------------------------------------


class TestEnumValidation:
    def test_valid_enum_values_accepted(self) -> None:
        config = InterviewConfiguration(**_valid_configuration_kwargs())
        assert config.career_level in constants.CAREER_LEVELS
        assert config.difficulty in constants.DIFFICULTY_LEVELS

    def test_invalid_career_level_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InterviewConfiguration(
                **{**_valid_configuration_kwargs(), "career_level": "wizard"}
            )

    def test_invalid_interview_type_in_list_rejected(self) -> None:
        with pytest.raises(ValidationError):
            InterviewConfiguration(
                **{**_valid_configuration_kwargs(), "interview_types": ["telepathy"]}
            )

    def test_invalid_input_difficulty_strictly_rejected(self) -> None:
        # Input difficulty stays strict (unlike a model's generated difficulty):
        # an unknown value is rejected, never coerced.
        with pytest.raises(ValidationError):
            InterviewConfiguration(
                **{**_valid_configuration_kwargs(), "difficulty": "impossible"}
            )

    def test_unapproved_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelSettings(model="anthropic/claude-not-approved")

    def test_all_approved_models_accepted(self) -> None:
        for model_id in constants.APPROVED_MODELS:
            assert ModelSettings(model=model_id).model == model_id

    def test_invalid_prompt_technique_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ModelSettings(prompt_technique="mind_reading")


# --- ModelSettings numeric bounds -------------------------------------------


class TestModelSettingsBounds:
    def test_defaults_come_from_constants(self) -> None:
        settings = ModelSettings()
        assert settings.model == constants.DEFAULT_MODEL
        assert settings.temperature == constants.DEFAULT_TEMPERATURE
        assert settings.max_tokens == constants.DEFAULT_MAX_OUTPUT_TOKENS
        assert settings.prompt_technique in constants.PROMPT_TECHNIQUES

    @pytest.mark.parametrize(
        "temperature", [constants.MIN_TEMPERATURE, constants.MAX_TEMPERATURE]
    )
    def test_temperature_bounds_accepted(self, temperature: float) -> None:
        assert ModelSettings(temperature=temperature).temperature == temperature

    @pytest.mark.parametrize(
        "temperature",
        [constants.MIN_TEMPERATURE - 0.1, constants.MAX_TEMPERATURE + 0.1],
    )
    def test_temperature_out_of_bounds_rejected(self, temperature: float) -> None:
        with pytest.raises(ValidationError):
            ModelSettings(temperature=temperature)

    @pytest.mark.parametrize(
        "max_tokens",
        [constants.MIN_OUTPUT_TOKENS - 1, constants.MAX_OUTPUT_TOKENS_LIMIT + 1],
    )
    def test_max_tokens_out_of_bounds_rejected(self, max_tokens: int) -> None:
        with pytest.raises(ValidationError):
            ModelSettings(max_tokens=max_tokens)


# --- Number-of-questions bounds ---------------------------------------------


class TestNumberOfQuestionsBounds:
    def test_default_is_within_bounds(self) -> None:
        config = InterviewConfiguration(**_valid_configuration_kwargs())
        assert (
            constants.MIN_QUESTIONS
            <= config.number_of_questions
            <= constants.MAX_QUESTIONS
        )

    @pytest.mark.parametrize(
        "count", [constants.MIN_QUESTIONS, constants.MAX_QUESTIONS]
    )
    def test_boundary_counts_accepted(self, count: int) -> None:
        config = InterviewConfiguration(
            **{**_valid_configuration_kwargs(), "number_of_questions": count}
        )
        assert config.number_of_questions == count

    @pytest.mark.parametrize(
        "count", [constants.MIN_QUESTIONS - 1, constants.MAX_QUESTIONS + 1]
    )
    def test_out_of_range_counts_rejected(self, count: int) -> None:
        with pytest.raises(ValidationError):
            InterviewConfiguration(
                **{**_valid_configuration_kwargs(), "number_of_questions": count}
            )


# --- Score-range boundaries --------------------------------------------------


class TestScoreRanges:
    @pytest.mark.parametrize(
        "overall", [constants.MIN_OVERALL_SCORE, constants.MAX_OVERALL_SCORE]
    )
    def test_overall_score_boundaries_accepted(self, overall: int) -> None:
        evaluation = AnswerEvaluation(
            **{**_valid_evaluation_kwargs(), "overall_score": overall}
        )
        assert evaluation.overall_score == overall

    @pytest.mark.parametrize(
        "overall", [constants.MIN_OVERALL_SCORE - 1, constants.MAX_OVERALL_SCORE + 1]
    )
    def test_overall_score_out_of_range_rejected(self, overall: int) -> None:
        with pytest.raises(ValidationError):
            AnswerEvaluation(
                **{**_valid_evaluation_kwargs(), "overall_score": overall}
            )

    @pytest.mark.parametrize(
        "score", [constants.MIN_RUBRIC_SCORE, constants.MAX_RUBRIC_SCORE]
    )
    def test_rubric_score_boundaries_accepted(self, score: int) -> None:
        evaluation = AnswerEvaluation(
            **{**_valid_evaluation_kwargs(), "relevance": score}
        )
        assert evaluation.relevance == score

    @pytest.mark.parametrize(
        "score", [constants.MIN_RUBRIC_SCORE - 1, constants.MAX_RUBRIC_SCORE + 1]
    )
    def test_rubric_score_out_of_range_rejected(self, score: int) -> None:
        with pytest.raises(ValidationError):
            AnswerEvaluation(**{**_valid_evaluation_kwargs(), "communication": score})

    def test_report_readiness_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FinalInterviewReport(
                **{**_valid_report_kwargs(), "overall_readiness_score": 150}
            )


# --- InterviewQuestion -------------------------------------------------------


class TestInterviewQuestion:
    def test_valid_question_builds(self) -> None:
        question = InterviewQuestion(**_valid_question_kwargs())
        assert question.question_id == 1
        assert question.question_type in constants.INTERVIEW_TYPES

    def test_question_id_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            InterviewQuestion(**{**_valid_question_kwargs(), "question_id": 0})

    def test_unmappable_question_type_coerced_to_default(self) -> None:
        # question_type is a descriptive label the model invents; an
        # unrecognised value is recorded as the safe default, not rejected, so a
        # whole interview never fails over a metadata tag.
        question = InterviewQuestion(
            **{**_valid_question_kwargs(), "question_type": "riddle"}
        )
        assert question.question_type == "behavioural"

    @pytest.mark.parametrize(
        "given, expected",
        [
            ("moderate", "moderate"),
            ("Moderate", "moderate"),  # case
            ("  HARD  ", "hard"),  # case + whitespace
            ("medium", "moderate"),  # synonym
            ("intermediate", "moderate"),  # synonym
            ("challenging", "hard"),  # synonym
            ("basic", "easy"),  # synonym
        ],
    )
    def test_difficulty_variants_normalise_to_canonical(
        self, given: str, expected: str
    ) -> None:
        question = InterviewQuestion(
            **{**_valid_question_kwargs(), "difficulty": given}
        )
        assert question.difficulty == expected

    @pytest.mark.parametrize(
        "given, expected",
        [
            ("behavioural", "behavioural"),
            ("behavioral", "behavioural"),  # US spelling
            ("Behavioural", "behavioural"),  # case
            ("case study", "case_study"),  # space → underscore
            ("case-study", "case_study"),  # hyphen → underscore
            ("culture fit", "culture_values"),  # synonym + space
        ],
    )
    def test_question_type_variants_normalise_to_canonical(
        self, given: str, expected: str
    ) -> None:
        question = InterviewQuestion(
            **{**_valid_question_kwargs(), "question_type": given}
        )
        assert question.question_type == expected

    def test_unmappable_difficulty_coerced_to_default(self) -> None:
        # In generated output an unknown difficulty is recorded as the safe
        # default rather than failing the interview.
        question = InterviewQuestion(
            **{**_valid_question_kwargs(), "difficulty": "impossible"}
        )
        assert question.difficulty == "moderate"


# --- UsageRecord -------------------------------------------------------------


class TestUsageRecord:
    def test_valid_record_builds_and_defaults_to_usd(self) -> None:
        record = UsageRecord(**_valid_usage_kwargs())
        assert record.currency == "USD"
        assert record.total_tokens == record.prompt_tokens + record.completion_tokens

    def test_currency_is_uppercased(self) -> None:
        record = UsageRecord(**{**_valid_usage_kwargs(), "currency": "usd"})
        assert record.currency == "USD"

    def test_non_usd_currency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(**{**_valid_usage_kwargs(), "currency": "EUR"})

    def test_token_total_mismatch_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(**{**_valid_usage_kwargs(), "total_tokens": 999})

    def test_negative_tokens_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(**{**_valid_usage_kwargs(), "prompt_tokens": -1})

    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(**{**_valid_usage_kwargs(), "calculated_cost": -0.01})

    def test_reported_source_requires_reported_cost(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(
                **{
                    **_valid_usage_kwargs(),
                    "cost_source": "reported",
                    "reported_cost": None,
                }
            )

    def test_reported_source_with_cost_accepted(self) -> None:
        record = UsageRecord(
            **{
                **_valid_usage_kwargs(),
                "cost_source": "reported",
                "reported_cost": 0.0031,
            }
        )
        assert record.reported_cost == 0.0031

    def test_unapproved_model_rejected(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(**{**_valid_usage_kwargs(), "model": "openai/gpt-4o"})


# --- Unknown-field rejection -------------------------------------------------


class TestUnknownFields:
    def test_unknown_field_rejected_on_configuration(self) -> None:
        with pytest.raises(ValidationError):
            InterviewConfiguration(
                **{**_valid_configuration_kwargs(), "secret_flag": True}
            )

    def test_unknown_field_ignored_on_generated_model(self) -> None:
        # Generated (model-output) schemas ignore surplus keys the model may
        # add, rather than failing the whole response. The extra data is
        # dropped, so a stray field such as chain_of_thought never reaches the
        # validated object or the UI — the no-hidden-reasoning guard still holds.
        evaluation = AnswerEvaluation(
            **{**_valid_evaluation_kwargs(), "chain_of_thought": "hidden"}
        )
        assert not hasattr(evaluation, "chain_of_thought")
        assert "chain_of_thought" not in evaluation.model_dump()

    def test_unknown_field_rejected_on_usage(self) -> None:
        with pytest.raises(ValidationError):
            UsageRecord(**{**_valid_usage_kwargs(), "injected": "x"})


# --- Structured outputs build end to end ------------------------------------


class TestStructuredOutputsBuild:
    def test_strategy_builds(self) -> None:
        strategy = InterviewStrategy(**_valid_strategy_kwargs())
        assert len(strategy.preparation_priorities) >= 1

    def test_evaluation_builds(self) -> None:
        evaluation = AnswerEvaluation(**_valid_evaluation_kwargs())
        assert evaluation.overall_score == 72

    def test_text_field_given_as_list_is_flattened(self) -> None:
        # Models often answer a free-text field (e.g. a suggested structure)
        # with a list of steps instead of a sentence. It is flattened to a
        # readable string rather than failing validation.
        evaluation = AnswerEvaluation(
            **{
                **_valid_evaluation_kwargs(),
                "stronger_answer_structure": ["Situation", "Task", "Action", "Result"],
            }
        )
        assert isinstance(evaluation.stronger_answer_structure, str)
        assert evaluation.stronger_answer_structure == "Situation\nTask\nAction\nResult"

    def test_text_field_given_as_object_is_flattened(self) -> None:
        evaluation = AnswerEvaluation(
            **{
                **_valid_evaluation_kwargs(),
                "stronger_answer_structure": {"situation": "x", "task": "y"},
            }
        )
        assert isinstance(evaluation.stronger_answer_structure, str)
        assert "situation: x" in evaluation.stronger_answer_structure

    def test_list_field_is_not_stringified(self) -> None:
        # Coercion targets string fields only; genuine list fields stay lists.
        evaluation = AnswerEvaluation(
            **{**_valid_evaluation_kwargs(), "strengths": ["clear", "concise"]}
        )
        assert evaluation.strengths == ["clear", "concise"]

    def test_report_builds(self) -> None:
        report = FinalInterviewReport(**_valid_report_kwargs())
        assert report.overall_readiness_score == 68
