"""Registry of prompt-engineering techniques.

A thin, UI-friendly catalogue over :mod:`src.prompts`. It pairs each stable
technique ID with human-readable metadata (name, description, recommended use
case) and the builder that produces the system prompt. The Streamlit layer can
render a selector from :func:`selector_options` without knowing anything about
how the prompts are built, and unsupported IDs are rejected with a clear,
controlled error rather than a crash or a silent default.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from src import constants
from src.models import InterviewConfiguration
from src.prompts import SYSTEM_PROMPT_BUILDERS, TARGET_SCHEMA_NAME

__all__ = [
    "PromptTechniqueSpec",
    "UnknownPromptTechniqueError",
    "list_techniques",
    "technique_ids",
    "get_technique",
    "selector_options",
    "format_option",
]


class UnknownPromptTechniqueError(KeyError):
    """Raised when a technique ID is not registered.

    Subclasses ``KeyError`` so existing ``except KeyError`` handlers still
    catch it, while giving callers a specific, catchable type.
    """


@dataclass(frozen=True)
class PromptTechniqueSpec:
    """Everything the app needs to present and use one technique."""

    technique_id: str
    name: str
    description: str
    use_case: str
    build_system_prompt: Callable[[InterviewConfiguration], str]


# Human-readable metadata, keyed by the stable IDs in
# ``constants.PROMPT_TECHNIQUES``. The order of that tuple defines display
# order in the UI.
_TECHNIQUE_METADATA: dict[str, dict[str, str]] = {
    "zero_shot": {
        "name": "Zero-shot instruction",
        "description": (
            "Gives the model the task and rubric directly, with no worked "
            "examples, and asks for the structured evaluation."
        ),
        "use_case": (
            "A fast, low-token baseline and the control condition for the "
            "prompt-comparison experiment."
        ),
    },
    "role_persona": {
        "name": "Role and persona prompting",
        "description": (
            "Asks the model to adopt an experienced interviewer persona for "
            "the target role and sector before evaluating."
        ),
        "use_case": (
            "When role-specific tone and expertise should shape which "
            "strengths and gaps are emphasised."
        ),
    },
    "few_shot": {
        "name": "Few-shot prompting",
        "description": (
            "Shows one profession-neutral worked example — a weak answer, its "
            "structured evaluation, and an improved example answer — before the "
            "real evaluation."
        ),
        "use_case": (
            "When consistency of format and scoring standard matters most; "
            "anchors the model to the expected pattern."
        ),
    },
    "structured_procedure": {
        "name": "Structured analytical procedure",
        "description": (
            "Directs the model through a visible six-step analysis (purpose, "
            "claims, evidence, relevance, rubric, output) and returns only the "
            "final result."
        ),
        "use_case": (
            "When thorough, auditable evaluation of evidence and relevance is "
            "the priority."
        ),
    },
    "rubric_json": {
        "name": "Rubric-constrained structured output",
        "description": (
            "Spells out each rubric criterion and enforces strict adherence to "
            f"the {TARGET_SCHEMA_NAME} JSON schema."
        ),
        "use_case": (
            "When reliable, machine-parseable JSON and tight rubric alignment "
            "are the priority."
        ),
    },
}


def _build_registry() -> dict[str, PromptTechniqueSpec]:
    """Construct the registry, keeping IDs, metadata and builders in lock-step."""
    registry: dict[str, PromptTechniqueSpec] = {}
    for technique_id in constants.PROMPT_TECHNIQUES:
        metadata = _TECHNIQUE_METADATA.get(technique_id)
        builder = SYSTEM_PROMPT_BUILDERS.get(technique_id)
        if metadata is None or builder is None:
            # A configuration mistake, surfaced loudly at import time rather
            # than as a confusing runtime gap later.
            raise RuntimeError(
                f"Prompt technique {technique_id!r} is missing metadata or a "
                "builder; constants, prompts and registry are out of sync."
            )
        registry[technique_id] = PromptTechniqueSpec(
            technique_id=technique_id,
            name=metadata["name"],
            description=metadata["description"],
            use_case=metadata["use_case"],
            build_system_prompt=builder,
        )
    return registry


_REGISTRY: dict[str, PromptTechniqueSpec] = _build_registry()


def technique_ids() -> list[str]:
    """Return the supported technique IDs in display order."""
    return list(_REGISTRY)


def list_techniques() -> list[PromptTechniqueSpec]:
    """Return all technique specs in display order."""
    return list(_REGISTRY.values())


def get_technique(technique_id: str) -> PromptTechniqueSpec:
    """Return the spec for ``technique_id``.

    Raises :class:`UnknownPromptTechniqueError` for unsupported IDs so callers
    fail safely with an explicit, catchable error.
    """
    try:
        return _REGISTRY[technique_id]
    except KeyError:
        raise UnknownPromptTechniqueError(
            f"Unknown prompt technique {technique_id!r}; "
            f"supported IDs are {technique_ids()}"
        ) from None


def selector_options() -> list[tuple[str, str]]:
    """Return ``(technique_id, name)`` pairs for a Streamlit selector.

    Use with ``st.selectbox(options=[id for id, _ in ...], format_func=...)``
    or pair with :func:`format_option`.
    """
    return [(spec.technique_id, spec.name) for spec in _REGISTRY.values()]


def format_option(technique_id: str) -> str:
    """Return the display label for a technique ID (for ``format_func``)."""
    return get_technique(technique_id).name
