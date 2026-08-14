"""Validated domain models and structured-output schemas.

Every value that flows between the UI, the (later) OpenRouter client and the
report layer is described here as a Pydantic model. Validating at the edges
means the rest of the application can trust its data: strings are already
stripped and non-empty, choices are known-good, and scores sit inside their
rubric ranges.

Design rules followed throughout this module:

* Surrounding whitespace is stripped from every string field.
* Required text and required lists reject empty / whitespace-only content.
* "Choose one of a set" fields are validated against the tuples in
  :mod:`src.constants` (the single source of truth) rather than hard-coding
  allowed values here.
* Numeric scores are range-checked.
* Unknown fields are rejected (``extra="forbid"``) so a typo or an injected
  key surfaces as an error instead of being silently ignored.
* There are no mutable default values.
* Every model is profession-neutral, stores no protected demographic
  information, and contains no hidden chain-of-thought field — feedback is
  concise and structured.
"""

from __future__ import annotations

import logging
import re
from typing import Annotated

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src import constants

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "InterviewConfiguration",
    "ModelSettings",
    "InterviewStrategy",
    "InterviewQuestion",
    "AnswerEvaluation",
    "FinalInterviewReport",
    "UsageRecord",
    "ModelPricing",
    "BranchQuestion",
    "ExternalServiceUsage",
]


# --- Shared base -------------------------------------------------------------


class _StudioModel(BaseModel):
    """Base model with the project-wide validation policy.

    ``str_strip_whitespace`` trims every string field, ``extra="forbid"``
    rejects unknown keys, and ``validate_assignment`` means later mutation is
    validated too — not just construction.
    """

    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
        validate_assignment=True,
    )


def _stringify_text(value: object) -> str:
    """Flatten a non-string model value into readable single-string text.

    A model often answers a free-text field with a list of steps or a small
    object (``["Situation", "Task", ...]`` or ``{"situation": "…"}``) instead of
    a sentence. Rather than reject it, join it into one readable string. Nested
    lists/objects are flattened recursively; a plain scalar becomes ``str``.
    """
    if isinstance(value, list):
        parts = [_stringify_text(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        return "\n".join(
            f"{key}: {_stringify_text(val)}" for key, val in value.items()
        )
    return str(value)


class _GeneratedModel(_StudioModel):
    """Base for objects parsed from *model output* (not user input).

    It differs from :class:`_StudioModel` in two model-tolerant ways, applied
    only to generated output (never to user input, which stays strict):

    * Unknown keys are **ignored** rather than rejected — a model routinely adds
      a well-meant surplus field, and failing the whole interview over an extra
      tag is the wrong trade-off.
    * A text field that arrives as a **list or object** is flattened to a
      string, because a model often answers a free-text field (e.g.
      ``stronger_answer_structure``) with a list of steps instead of a sentence.

    Every *required* field is still validated, so missing or malformed values
    are still rejected and nothing is invented — and the raw text has already
    passed the output safety scan before it reaches here.
    """

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _coerce_text_fields(cls, data: object) -> object:
        """Coerce a non-string value in a string field into readable text."""
        if not isinstance(data, dict):
            return data
        coerced = dict(data)
        for name, field in cls.model_fields.items():
            if field.annotation is str and name in coerced:
                value = coerced[name]
                if value is not None and not isinstance(value, str):
                    coerced[name] = _stringify_text(value)
        return coerced


# --- Reusable validators and field types ------------------------------------


def _clean_str_list(values: list[str]) -> list[str]:
    """Strip each item and reject blank / whitespace-only entries.

    ``str_strip_whitespace`` handles individual strings, but a list can still
    smuggle in an empty item; this closes that gap.
    """
    cleaned = [value.strip() for value in values]
    if any(value == "" for value in cleaned):
        raise ValueError("each item must be non-empty text, not blank or whitespace")
    return cleaned


def _normalise_enum_key(value: str) -> str:
    """Fold a label to a comparison key: lower-case, spaces/hyphens → ``_``.

    This lets a fixed vocabulary accept the harmless surface variants a model
    naturally produces (``"Case Study"``, ``"case-study"``, ``"MODERATE"``)
    while still mapping onto exactly one canonical value.
    """
    return re.sub(r"[\s\-]+", "_", value.strip().lower())


def _make_enum_type(
    allowed: tuple[str, ...],
    label: str,
    synonyms: dict[str, str] | None = None,
):
    """Build an ``Annotated[str, ...]`` type restricted to ``allowed``.

    Matching is tolerant but closed: the incoming value is normalised (case,
    whitespace and hyphens) and matched against the allowed set, then against
    an optional ``synonyms`` map (e.g. US spelling or common wording the model
    emits). The **canonical** allowed value is always returned, so downstream
    code only ever sees one spelling. Anything that matches neither is still
    rejected, so the vocabulary stays fixed and injected values are refused.
    """
    canonical = {_normalise_enum_key(value): value for value in allowed}
    synonym_keys = {
        _normalise_enum_key(key): value for key, value in (synonyms or {}).items()
    }

    def _check(value: str) -> str:
        if not isinstance(value, str):
            raise ValueError(f"{label} must be a string; got {value!r}")
        key = _normalise_enum_key(value)
        if key in canonical:
            return canonical[key]
        if key in synonym_keys:
            return synonym_keys[key]
        raise ValueError(
            f"{label} must be one of {list(allowed)}; got {value!r}"
        )

    return Annotated[str, AfterValidator(_check)]


def _make_lenient_enum_type(
    allowed: tuple[str, ...],
    label: str,
    default: str,
    synonyms: dict[str, str] | None = None,
):
    """Like :func:`_make_enum_type`, but coerces an unknown value to ``default``.

    This is used only for the descriptive classification fields the model
    *invents* in its output (a question's ``question_type`` and ``difficulty``).
    Those are open-ended labels — a model may reasonably answer ``"motivational"``
    or ``"system_design"`` — and failing the whole interview over a metadata tag
    is worse than recording the nearest in-vocabulary value. Case/whitespace and
    the synonym map are applied first; anything still unmatched is logged and
    mapped to ``default`` (always a member of ``allowed``). This never runs on
    user-supplied input, so input validation stays strict.
    """
    canonical = {_normalise_enum_key(value): value for value in allowed}
    synonym_keys = {
        _normalise_enum_key(key): value for key, value in (synonyms or {}).items()
    }
    if default not in allowed:  # pragma: no cover - guards a programming error
        raise ValueError(f"default {default!r} is not in the allowed {label} set")

    def _check(value: str) -> str:
        if isinstance(value, str):
            key = _normalise_enum_key(value)
            if key in canonical:
                return canonical[key]
            if key in synonym_keys:
                return synonym_keys[key]
        _LOGGER.warning(
            "Coerced unrecognised %s %r to default %r", label, value, default
        )
        return default

    return Annotated[str, AfterValidator(_check)]


def _make_enum_list_type(allowed: tuple[str, ...], label: str):
    """Build a non-empty list type whose items are all in ``allowed``."""

    def _check(values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            value = value.strip()
            if value not in allowed:
                raise ValueError(
                    f"each {label} must be one of {list(allowed)}; got {value!r}"
                )
            cleaned.append(value)
        return cleaned

    return Annotated[
        list[str],
        Field(min_length=1, max_length=constants.MAX_LIST_ITEMS),
        AfterValidator(_check),
    ]


# Short required text (names, roles, single competencies).
ShortText = Annotated[str, Field(min_length=1, max_length=constants.MAX_SHORT_TEXT_CHARS)]

# Longer required free text (summaries, example answers, questions).
FreeText = Annotated[str, Field(min_length=1, max_length=constants.MAX_FREE_TEXT_CHARS)]

# A required, non-empty list of non-empty strings.
StrList = Annotated[
    list[str],
    Field(min_length=1, max_length=constants.MAX_LIST_ITEMS),
    AfterValidator(_clean_str_list),
]

# Common surface variants a model emits for the two enums it fills in freely
# (question difficulty and question type). Each maps onto a canonical value in
# the relevant constants tuple; case/space/hyphen differences are handled by the
# normaliser and need no entry here.
_DIFFICULTY_SYNONYMS = {
    "medium": "moderate",
    "intermediate": "moderate",
    "normal": "moderate",
    "difficult": "hard",
    "challenging": "hard",
    "advanced": "hard",
    "tough": "hard",
    "simple": "easy",
    "basic": "easy",
    "beginner": "easy",
}
_QUESTION_TYPE_SYNONYMS = {
    "behavioral": "behavioural",  # US spelling
    "competency_based": "competency",
    "competencies": "competency",
    "case": "case_study",
    "culture": "culture_values",
    "values": "culture_values",
    "culture_fit": "culture_values",
    "cultural_fit": "culture_values",
    "board": "executive_board",
    "stakeholder_management": "stakeholder",
}

# Enum-like scalar types for validated INPUT (strict — an unknown value is
# rejected). These guard user- and programmatically-supplied configuration.
CareerLevel = _make_enum_type(constants.CAREER_LEVELS, "career_level")
InterviewerPersona = _make_enum_type(constants.INTERVIEWER_PERSONAS, "interviewer_persona")
Difficulty = _make_enum_type(
    constants.DIFFICULTY_LEVELS, "difficulty", synonyms=_DIFFICULTY_SYNONYMS
)
BranchMode = _make_enum_type(constants.BRANCH_MODES, "branch_mode")
ResponseDetail = _make_enum_type(constants.RESPONSE_DETAIL_LEVELS, "response_detail")
PromptTechnique = _make_enum_type(constants.PROMPT_TECHNIQUES, "prompt_technique")
CostSource = _make_enum_type(constants.COST_SOURCES, "cost_source")
ApprovedModel = _make_enum_type(tuple(constants.APPROVED_MODELS), "model")

# Classification fields the MODEL fills in freely in its output. These are
# lenient: a value that cannot be mapped to the vocabulary is recorded as the
# nearest safe default (and logged) rather than failing the whole interview
# over a descriptive tag. Used only in generated output, never on input.
ModelDifficulty = _make_lenient_enum_type(
    constants.DIFFICULTY_LEVELS,
    "difficulty",
    default="moderate",
    synonyms=_DIFFICULTY_SYNONYMS,
)
QuestionType = _make_lenient_enum_type(
    constants.INTERVIEW_TYPES,
    "question_type",
    default="behavioural",
    synonyms=_QUESTION_TYPE_SYNONYMS,
)

# Enum-like list type.
InterviewTypeList = _make_enum_list_type(constants.INTERVIEW_TYPES, "interview type")

# Numeric field types.
NumberOfQuestions = Annotated[
    int, Field(ge=constants.MIN_QUESTIONS, le=constants.MAX_QUESTIONS)
]
Temperature = Annotated[
    float, Field(ge=constants.MIN_TEMPERATURE, le=constants.MAX_TEMPERATURE)
]
MaxTokens = Annotated[
    int, Field(ge=constants.MIN_OUTPUT_TOKENS, le=constants.MAX_OUTPUT_TOKENS_LIMIT)
]
OverallScore = Annotated[
    int, Field(ge=constants.MIN_OVERALL_SCORE, le=constants.MAX_OVERALL_SCORE)
]
RubricScore = Annotated[
    int, Field(ge=constants.MIN_RUBRIC_SCORE, le=constants.MAX_RUBRIC_SCORE)
]


# --- Input models ------------------------------------------------------------


class InterviewConfiguration(_StudioModel):
    """What the candidate wants to practise.

    Assembled from the UI. Optional context fields default to an empty string
    and are length-limited because they carry untrusted, pasted content.
    """

    target_role: ShortText = Field(
        description="Role the candidate is preparing for, e.g. 'Registered Nurse'."
    )
    industry_or_sector: ShortText = Field(
        description="Industry or sector context, e.g. 'healthcare' or 'fintech'."
    )
    career_level: CareerLevel = Field(
        description="Seniority band; one of the profession-neutral career levels."
    )
    company_context: str = Field(
        default="",
        max_length=constants.MAX_FREE_TEXT_CHARS,
        description="Optional notes about the employer or team (untrusted input).",
    )
    job_description: str = Field(
        default="",
        max_length=constants.MAX_JOB_DESCRIPTION_CHARS,
        description="Optional pasted job description (untrusted input).",
    )
    candidate_background: str = Field(
        default="",
        max_length=constants.MAX_CANDIDATE_BACKGROUND_CHARS,
        description="Optional short candidate background summary (untrusted input).",
    )
    interview_types: InterviewTypeList = Field(
        description="One or more interview types to practise."
    )
    interviewer_persona: InterviewerPersona = Field(
        description="Tone the interviewer should adopt."
    )
    difficulty: Difficulty = Field(
        description="Overall difficulty band for the session."
    )
    number_of_questions: NumberOfQuestions = Field(
        default=constants.DEFAULT_NUMBER_OF_QUESTIONS,
        description="How many questions to generate for the session.",
    )
    response_detail: ResponseDetail = Field(
        description="How detailed the interviewer's feedback should be."
    )


class ModelSettings(_StudioModel):
    """Generation settings for a single OpenRouter request."""

    model: ApprovedModel = Field(
        default=constants.DEFAULT_MODEL,
        description="Approved OpenRouter model identifier.",
    )
    temperature: Temperature = Field(
        default=constants.DEFAULT_TEMPERATURE,
        description="Sampling temperature within the allowed range.",
    )
    max_tokens: MaxTokens = Field(
        default=constants.DEFAULT_MAX_OUTPUT_TOKENS,
        description="Maximum output tokens within the allowed range.",
    )
    prompt_technique: PromptTechnique = Field(
        default=constants.PROMPT_TECHNIQUES[0],
        description="Which system-prompt technique to use for this request.",
    )


# --- Structured-output models ------------------------------------------------


class InterviewStrategy(_GeneratedModel):
    """A preparation strategy the model produces for the chosen role.

    Every list section must contain at least one concrete item; an empty
    section is treated as an incomplete response and rejected.
    """

    role_summary: FreeText = Field(
        description="Concise summary of the role and what success looks like."
    )
    likely_interview_stages: StrList = Field(
        description="Ordered stages the process is likely to include."
    )
    critical_competencies: StrList = Field(
        description="Competencies most likely to be assessed."
    )
    likely_question_themes: StrList = Field(
        description="Themes questions are likely to cluster around."
    )
    probable_challenges: StrList = Field(
        description="Challenges or tough areas the candidate should anticipate."
    )
    evidence_to_prepare: StrList = Field(
        description="Concrete examples and evidence the candidate should ready."
    )
    technical_or_functional_topics: StrList = Field(
        description="Technical or functional topics to revise for the role."
    )
    behavioural_topics: StrList = Field(
        description="Behavioural themes likely to be explored."
    )
    questions_for_interviewer: StrList = Field(
        description="Thoughtful questions the candidate could ask the interviewer."
    )
    preparation_priorities: StrList = Field(
        description="Ranked priorities for the candidate's preparation time."
    )


class InterviewQuestion(_GeneratedModel):
    """A single interview question with its assessment intent."""

    question_id: int = Field(
        ge=1, description="Positive, session-unique question identifier."
    )
    question: FreeText = Field(description="The question text put to the candidate.")
    question_type: QuestionType = Field(
        description="Interview type this question belongs to."
    )
    competency: ShortText = Field(
        description="Primary competency the question assesses."
    )
    difficulty: ModelDifficulty = Field(
        description="Difficulty band for this question."
    )
    interviewer_intent: FreeText = Field(
        description="Concise note on what a strong answer should demonstrate "
        "(a rubric hint, not hidden reasoning)."
    )
    expected_answer_elements: StrList = Field(
        description="Key elements a strong answer would include."
    )


class AnswerEvaluation(_GeneratedModel):
    """Structured, rubric-based feedback on one candidate answer.

    Scores are practice feedback only and never an objective hiring decision.
    """

    overall_score: OverallScore = Field(
        description="Overall practice score from 0 to 100."
    )
    relevance: RubricScore = Field(description="Relevance to the question (1-10).")
    structure: RubricScore = Field(description="Answer structure and clarity (1-10).")
    evidence: RubricScore = Field(
        description="Use of concrete evidence and examples (1-10)."
    )
    role_knowledge: RubricScore = Field(
        description="Demonstrated role or domain knowledge (1-10)."
    )
    problem_solving: RubricScore = Field(
        description="Problem-solving and reasoning quality (1-10)."
    )
    communication: RubricScore = Field(
        description="Communication and delivery (1-10)."
    )
    credibility: RubricScore = Field(
        description="Credibility and consistency of the answer (1-10)."
    )
    strengths: StrList = Field(description="What the candidate did well.")
    improvement_areas: StrList = Field(
        description="Specific areas to improve next time."
    )
    missing_evidence: StrList = Field(
        description="Evidence or detail that was missing from the answer."
    )
    stronger_answer_structure: FreeText = Field(
        description="A suggested structure for a stronger answer."
    )
    improved_example_answer: FreeText = Field(
        description="A concise improved example answer (illustrative only)."
    )
    follow_up_question: FreeText = Field(
        description="A natural follow-up question the interviewer might ask."
    )


class FinalInterviewReport(_GeneratedModel):
    """End-of-session summary across all answers."""

    overall_readiness_score: OverallScore = Field(
        description="Overall readiness score from 0 to 100 (practice feedback)."
    )
    performance_summary: FreeText = Field(
        description="Concise narrative summary of the session."
    )
    strongest_competencies: StrList = Field(
        description="Competencies the candidate demonstrated most strongly."
    )
    development_priorities: StrList = Field(
        description="Highest-value areas to develop before the real interview."
    )
    recurring_answer_patterns: StrList = Field(
        description="Patterns seen across multiple answers, good or bad."
    )
    highest_risk_questions: StrList = Field(
        description="Questions the candidate is least ready for."
    )
    evidence_gaps: StrList = Field(
        description="Recurring gaps in concrete evidence or examples."
    )
    recommended_practice_actions: StrList = Field(
        description="Actionable next steps for further practice."
    )
    final_interview_checklist: StrList = Field(
        description="A short checklist to run through before the real interview."
    )


# --- Usage / cost model ------------------------------------------------------


class UsageRecord(_StudioModel):
    """Token and cost accounting for a single OpenRouter request.

    Costs are recorded in US dollars because OpenRouter reports spend in USD.
    ``reported_cost`` is the provider-supplied figure when available;
    ``calculated_cost`` is always present (derived locally from token counts).
    """

    model: ApprovedModel = Field(
        description="Approved model identifier the request used."
    )
    prompt_tokens: int = Field(ge=0, description="Tokens in the prompt.")
    completion_tokens: int = Field(ge=0, description="Tokens in the completion.")
    total_tokens: int = Field(
        ge=0, description="Total tokens; must equal prompt + completion."
    )
    reported_cost: float | None = Field(
        default=None,
        ge=0,
        description="Provider-reported cost in USD, if available.",
    )
    calculated_cost: float = Field(
        ge=0, description="Locally calculated cost in USD."
    )
    cost_source: CostSource = Field(
        description="Where the authoritative cost figure came from."
    )
    currency: str = Field(
        default=constants.DEFAULT_CURRENCY,
        description="ISO currency code; USD for OpenRouter.",
    )
    request_duration_seconds: float = Field(
        ge=0, description="Wall-clock request duration in seconds."
    )

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        """Only USD is supported (OpenRouter reports in US dollars)."""
        value = value.upper()
        if value not in constants.SUPPORTED_CURRENCIES:
            raise ValueError(
                f"currency must be one of {list(constants.SUPPORTED_CURRENCIES)}; "
                f"got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _check_consistency(self) -> "UsageRecord":
        """Cross-field checks that individual fields cannot express."""
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise ValueError(
                "total_tokens must equal prompt_tokens + completion_tokens"
            )
        if self.cost_source == "reported" and self.reported_cost is None:
            raise ValueError(
                "reported_cost is required when cost_source is 'reported'"
            )
        return self


# --- Pricing metadata --------------------------------------------------------


class ModelPricing(_StudioModel):
    """Per-token pricing for one model, read from OpenRouter metadata.

    Prices are in US dollars per token (OpenRouter reports them as strings; the
    pricing service converts them). All prices must be non-negative. This is a
    validated record of external metadata — it is never hard-coded.
    """

    model_id: ShortText = Field(description="Model identifier the pricing applies to.")
    prompt_usd_per_token: float = Field(
        ge=0, description="USD charged per prompt (input) token."
    )
    completion_usd_per_token: float = Field(
        ge=0, description="USD charged per completion (output) token."
    )
    request_usd: float = Field(
        default=0.0, ge=0, description="Flat USD charged per request, if any."
    )
    currency: str = Field(
        default=constants.DEFAULT_CURRENCY,
        description="ISO currency code; USD for OpenRouter.",
    )

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        """Only USD is supported (OpenRouter reports in US dollars)."""
        value = value.upper()
        if value not in constants.SUPPORTED_CURRENCIES:
            raise ValueError(
                f"currency must be one of {list(constants.SUPPORTED_CURRENCIES)}; "
                f"got {value!r}"
            )
        return value


class ExternalServiceUsage(_StudioModel):
    """Usage/cost for a non-LLM external service (e.g. speech-to-text).

    Kept separate from :class:`UsageRecord` (LLM tokens) so each cost stream is
    reported honestly. ``cost_usd`` is ``None`` and ``cost_source`` is
    ``"unavailable"`` unless a real rate is known — pricing is never invented.
    """

    provider: ShortText = Field(description="External provider identifier.")
    operation: ShortText = Field(description="Operation performed, e.g. speech_to_text.")
    units: float = Field(ge=0, description="Billable units consumed (e.g. audio seconds).")
    unit_name: ShortText = Field(description="Name of the unit, e.g. audio_seconds.")
    cost_usd: float | None = Field(
        default=None, ge=0, description="USD cost, or None when not calculable."
    )
    cost_source: CostSource = Field(
        default="unavailable",
        description="How the cost was obtained: reported, calculated or unavailable.",
    )
    currency: str = Field(
        default=constants.DEFAULT_CURRENCY, description="ISO currency code; USD."
    )

    @field_validator("currency")
    @classmethod
    def _check_currency(cls, value: str) -> str:
        value = value.upper()
        if value not in constants.SUPPORTED_CURRENCIES:
            raise ValueError(
                f"currency must be one of {list(constants.SUPPORTED_CURRENCIES)}; "
                f"got {value!r}"
            )
        return value


# --- Interview Deep Dive (branching) -----------------------------------------


class BranchQuestion(_GeneratedModel):
    """A deeper "deep dive" question that branches from an evaluated answer.

    A branch question deepens the topic of a parent interview question using the
    candidate's actual answer; it is never counted as a scheduled main question.
    The linkage fields (``branch_id``, ``parent_question_id``, ``branch_mode``,
    ``depth``) are set authoritatively by the service, not invented by the model.
    """

    branch_id: ShortText = Field(description="Stable identifier for this branch turn.")
    parent_question_id: int = Field(
        ge=1, description="question_id of the main question this branch deepens."
    )
    question: FreeText = Field(description="The deeper deep-dive question text.")
    branch_mode: BranchMode = Field(
        description="Kind of deeper exploration (e.g. challenge_assumptions)."
    )
    focus_area: ShortText = Field(
        description="The specific aspect of the answer being probed."
    )
    interviewer_intent: FreeText = Field(
        description="Concise note on what a strong answer should demonstrate "
        "(a rubric hint, not hidden reasoning)."
    )
    expected_answer_elements: StrList = Field(
        description="Key elements a strong answer to this branch would include."
    )
    difficulty: ModelDifficulty = Field(
        description="Difficulty band for this branch."
    )
    depth: int = Field(
        ge=1,
        le=constants.MAX_BRANCH_DEPTH,
        description="Branch depth level (1..MAX_BRANCH_DEPTH).",
    )
