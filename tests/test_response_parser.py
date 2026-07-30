"""Tests for the safe response parser."""

import pytest

from src.models import AnswerEvaluation
from src.response_parser import (
    ResponseParseError,
    parse_json_object,
    parse_structured_output,
    strip_json_fences,
)


def _valid_evaluation_dict() -> dict:
    return {
        "overall_score": 70,
        "relevance": 7,
        "structure": 7,
        "evidence": 7,
        "role_knowledge": 7,
        "problem_solving": 7,
        "communication": 7,
        "credibility": 7,
        "strengths": ["clear"],
        "improvement_areas": ["add detail"],
        "missing_evidence": ["metrics"],
        "stronger_answer_structure": "STAR",
        "improved_example_answer": "Example to personalise.",
        "follow_up_question": "What changed?",
    }


def _valid_json() -> str:
    import json

    return json.dumps(_valid_evaluation_dict())


# --- Fence stripping ---------------------------------------------------------


class TestFenceStripping:
    def test_strips_json_fence(self) -> None:
        text = "```json\n{\"a\": 1}\n```"
        assert strip_json_fences(text) == '{"a": 1}'

    def test_strips_plain_fence(self) -> None:
        text = "```\n{\"a\": 1}\n```"
        assert strip_json_fences(text) == '{"a": 1}'

    def test_leaves_unfenced_text(self) -> None:
        assert strip_json_fences('{"a": 1}') == '{"a": 1}'

    def test_does_not_touch_inner_backticks(self) -> None:
        assert strip_json_fences('{"a": "b`c"}') == '{"a": "b`c"}'


# --- JSON object parsing -----------------------------------------------------


class TestJsonObjectParsing:
    def test_parses_object(self) -> None:
        assert parse_json_object('{"a": 1}') == {"a": 1}

    def test_empty_raises(self) -> None:
        with pytest.raises(ResponseParseError):
            parse_json_object("   ")

    def test_invalid_json_raises(self) -> None:
        with pytest.raises(ResponseParseError):
            parse_json_object("not json")

    def test_non_object_json_raises(self) -> None:
        with pytest.raises(ResponseParseError):
            parse_json_object("[1, 2, 3]")

    def test_code_like_payload_is_not_executed(self) -> None:
        # A Python expression is not valid JSON; it is rejected, never eval'd.
        with pytest.raises(ResponseParseError):
            parse_json_object("__import__('os').system('echo hi')")


# --- Structured output with repair ------------------------------------------


class TestStructuredOutput:
    def test_valid_output_parses(self) -> None:
        result = parse_structured_output(_valid_json(), AnswerEvaluation)
        assert isinstance(result, AnswerEvaluation)
        assert result.overall_score == 70

    def test_fenced_valid_output_parses(self) -> None:
        result = parse_structured_output(
            f"```json\n{_valid_json()}\n```", AnswerEvaluation
        )
        assert result.overall_score == 70

    def test_missing_values_are_not_invented(self) -> None:
        import json

        incomplete = _valid_evaluation_dict()
        del incomplete["follow_up_question"]
        with pytest.raises(ResponseParseError):
            parse_structured_output(json.dumps(incomplete), AnswerEvaluation)

    def test_out_of_range_score_rejected(self) -> None:
        import json

        bad = _valid_evaluation_dict()
        bad["overall_score"] = 500
        with pytest.raises(ResponseParseError):
            parse_structured_output(json.dumps(bad), AnswerEvaluation)

    def test_no_repair_raises_on_first_failure(self) -> None:
        with pytest.raises(ResponseParseError):
            parse_structured_output("not json", AnswerEvaluation)

    def test_one_repair_round_succeeds(self) -> None:
        calls = {"n": 0}

        def repair(bad: str, error: str) -> str:
            calls["n"] += 1
            return _valid_json()

        result = parse_structured_output(
            "not json", AnswerEvaluation, repair=repair
        )
        assert result.overall_score == 70
        assert calls["n"] == 1  # exactly one repair attempt

    def test_stops_after_second_failure(self) -> None:
        calls = {"n": 0}

        def repair(bad: str, error: str) -> str:
            calls["n"] += 1
            return "still not json"

        with pytest.raises(ResponseParseError) as exc:
            parse_structured_output("not json", AnswerEvaluation, repair=repair)
        assert calls["n"] == 1  # repair tried once, then stopped
        assert "repair" in exc.value.message.lower()

    def test_error_message_is_controlled_string(self) -> None:
        with pytest.raises(ResponseParseError) as exc:
            parse_structured_output("not json", AnswerEvaluation)
        assert isinstance(exc.value.message, str)
        assert exc.value.message  # non-empty, human-readable
