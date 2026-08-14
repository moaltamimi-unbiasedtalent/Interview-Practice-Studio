"""Tests for JSON Schema structured-output helpers.

No network and no Pydantic-schema duplication: the schema is always derived from
the model itself. These tests assert the *strict* shape providers require.
"""

from src.models import AnswerEvaluation, InterviewQuestion, InterviewStrategy
from src.structured_output import (
    build_strict_schema,
    build_structured_response_format,
)


def _assert_strict_objects(node) -> None:
    """Every object node forbids extras and requires all its properties."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(props.keys())
            for child in props.values():
                _assert_strict_objects(child)
        for key in ("items", "anyOf", "oneOf", "allOf"):
            value = node.get(key)
            if isinstance(value, dict):
                _assert_strict_objects(value)
            elif isinstance(value, list):
                for child in value:
                    _assert_strict_objects(child)
        defs = node.get("$defs")
        if isinstance(defs, dict):
            for child in defs.values():
                _assert_strict_objects(child)


class TestBuildStrictSchema:
    def test_schema_is_derived_from_the_model(self) -> None:
        schema = build_strict_schema(AnswerEvaluation)
        # Every declared field appears; nothing is hand-duplicated.
        assert set(schema["properties"]) == set(AnswerEvaluation.model_fields)

    def test_root_forbids_extra_properties_and_requires_all(self) -> None:
        schema = build_strict_schema(AnswerEvaluation)
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])

    def test_nested_objects_are_strict_too(self) -> None:
        # InterviewStrategy is list-heavy; walk the whole tree.
        _assert_strict_objects(build_strict_schema(InterviewStrategy))


class TestResponseFormat:
    def test_response_format_payload_shape(self) -> None:
        rf = build_structured_response_format(InterviewQuestion)
        assert rf["type"] == "json_schema"
        assert rf["json_schema"]["name"] == "InterviewQuestion"
        assert rf["json_schema"]["strict"] is True
        assert rf["json_schema"]["schema"]["additionalProperties"] is False

    def test_custom_name_is_used(self) -> None:
        rf = build_structured_response_format(InterviewQuestion, name="next_question")
        assert rf["json_schema"]["name"] == "next_question"
