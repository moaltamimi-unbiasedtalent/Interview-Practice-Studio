"""Safe parsing of model responses into validated Pydantic objects.

The model returns text that is *supposed* to be a single JSON object. This
module turns that text into a validated domain object, defensively:

* JSON is parsed with :func:`json.loads` — never ``eval``/``exec``.
* Markdown code fences (```json ... ```) are stripped first.
* The result is validated through the correct Pydantic model, so missing or
  malformed values are rejected — never silently invented.
* One automatic **repair** round is allowed: on the first failure an injected
  ``repair`` callable may ask the model to fix its JSON. Parsing stops after a
  second failure.
* Failures raise :class:`ResponseParseError` with a short, controlled message
  and no stack trace.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import TypeVar

from pydantic import BaseModel, ValidationError

__all__ = [
    "ResponseParseError",
    "strip_json_fences",
    "parse_json_object",
    "parse_structured_output",
]

ModelT = TypeVar("ModelT", bound=BaseModel)

# A repair callable receives the bad text and a short error description and
# returns a fresh attempt (typically by asking the model to fix its output).
RepairFn = Callable[[str, str], str]

# Matches a leading ```/```json fence and its closing fence.
_FENCE_OPEN = re.compile(r"^\s*```[a-zA-Z0-9_-]*\s*\n?")
_FENCE_CLOSE = re.compile(r"\n?\s*```\s*$")


class ResponseParseError(Exception):
    """Raised when a model response cannot be parsed and validated.

    ``message`` is safe to show to a user. The original exception, if any, is
    kept on ``__cause__`` for logging but never rendered by this class.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


def strip_json_fences(text: str) -> str:
    """Remove a surrounding Markdown code fence, if present.

    Only strips a fence that wraps the whole string; it never edits content
    inside the JSON. Safe on text that has no fence.
    """
    if text is None:
        return ""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = _FENCE_OPEN.sub("", stripped)
        stripped = _FENCE_CLOSE.sub("", stripped)
    return stripped.strip()


def parse_json_object(text: str) -> dict:
    """Parse ``text`` into a JSON object (dict), safely.

    Raises :class:`ResponseParseError` if the text is not valid JSON or is not
    a JSON object. Uses :func:`json.loads` only — never ``eval``/``exec``.
    """
    cleaned = strip_json_fences(text)
    if not cleaned:
        raise ResponseParseError("The model returned an empty response.")
    try:
        data = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ResponseParseError(
            "The model response was not valid JSON."
        ) from exc
    if not isinstance(data, dict):
        raise ResponseParseError(
            "The model response was valid JSON but not a JSON object."
        )
    return data


def _parse_once(
    text: str, schema: type[ModelT], overrides: dict | None = None
) -> ModelT:
    """Parse and validate one attempt, raising ResponseParseError on failure.

    ``overrides`` (if given) are applied to the parsed object **before**
    validation, so caller-authoritative fields (e.g. a branch's depth and
    linkage ids) always take precedence over — and are validated instead of —
    whatever the model produced for them.
    """
    data = parse_json_object(text)
    if overrides:
        data.update(overrides)
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        # Summarise which fields failed, without a stack trace or raw payload.
        fields = ", ".join(
            ".".join(str(part) for part in error["loc"]) for error in exc.errors()
        )
        detail = f" (problem fields: {fields})" if fields else ""
        raise ResponseParseError(
            f"The model response did not match the required {schema.__name__} "
            f"format{detail}."
        ) from exc


def parse_structured_output(
    text: str,
    schema: type[ModelT],
    *,
    repair: RepairFn | None = None,
    overrides: dict | None = None,
) -> ModelT:
    """Parse ``text`` into a validated ``schema`` instance, with one repair round.

    On the first failure, if ``repair`` is provided, it is called once to obtain
    a corrected attempt which is parsed again. A second failure stops the process
    and raises :class:`ResponseParseError`. ``repair`` is injected (not built
    here) so this module stays independent of the network and easy to test.
    ``overrides`` are applied to the parsed object before validation on every
    attempt (see :func:`_parse_once`).
    """
    try:
        return _parse_once(text, schema, overrides)
    except ResponseParseError as first_error:
        if repair is None:
            raise
        try:
            repaired = repair(text, first_error.message)
        except ResponseParseError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface as a controlled error
            raise ResponseParseError(
                "The automatic repair attempt could not be completed."
            ) from exc
        try:
            return _parse_once(repaired, schema, overrides)
        except ResponseParseError as second_error:
            raise ResponseParseError(
                "The model response could not be parsed after one repair "
                "attempt. Please try again."
            ) from second_error
