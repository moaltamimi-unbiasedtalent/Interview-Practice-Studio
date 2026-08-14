"""JSON Schema structured-output helpers.

OpenRouter (and the OpenAI-compatible providers behind it) can enforce a strict
JSON Schema on a model's response instead of merely asking for "some JSON". When
a provider enforces the schema, the returned text is guaranteed to be a JSON
object of the right *shape*, which removes almost all of the defensive
extract-parse-repair machinery.

This module builds that request from the project's existing Pydantic models —
the single source of truth — via :meth:`pydantic.BaseModel.model_json_schema`.
The generated schema is post-processed into the *strict* form providers require:

* every object sets ``additionalProperties: false`` (no arbitrary extra keys);
* every object lists all of its properties in ``required``.

The schema is only used to constrain generation; the returned object is still
validated by the Pydantic model afterwards, so nothing here weakens validation.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

__all__ = [
    "build_strict_schema",
    "build_structured_response_format",
]


def _strictify(node: Any) -> None:
    """Recursively enforce strict-schema rules in place.

    For every object node, forbid unknown properties and mark every declared
    property as required (both are hard requirements of provider strict mode).
    Recurses through ``properties``, ``items``, ``$defs`` and the
    ``anyOf``/``oneOf``/``allOf`` combinators so nested models and lists are
    covered too.
    """
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            node["additionalProperties"] = False
            node["required"] = list(properties.keys())
            for child in properties.values():
                _strictify(child)

        items = node.get("items")
        if items is not None:
            _strictify(items)

        defs = node.get("$defs")
        if isinstance(defs, dict):
            for child in defs.values():
                _strictify(child)

        for combinator in ("anyOf", "oneOf", "allOf"):
            branch = node.get(combinator)
            if isinstance(branch, list):
                for child in branch:
                    _strictify(child)
    elif isinstance(node, list):
        for child in node:
            _strictify(child)


def build_strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a strict JSON Schema derived from a Pydantic model.

    The schema is generated from the model (never hand-duplicated) and then
    tightened so no arbitrary extra properties are accepted and every property
    is required.
    """
    schema = model.model_json_schema()
    _strictify(schema)
    return schema


def build_structured_response_format(
    model: type[BaseModel], name: str | None = None
) -> dict[str, Any]:
    """Build the ``response_format`` payload for JSON Schema structured output.

    Shape expected by OpenRouter / OpenAI-compatible providers::

        {"type": "json_schema",
         "json_schema": {"name": ..., "strict": True, "schema": {...}}}

    ``name`` defaults to the model's class name (a valid schema identifier).
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name or model.__name__,
            "strict": True,
            "schema": build_strict_schema(model),
        },
    }
