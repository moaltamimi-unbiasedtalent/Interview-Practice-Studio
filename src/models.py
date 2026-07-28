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

__all__ = [
    "InterviewConfiguration",
    "ModelSettings",
    "InterviewStrategy",
    "InterviewQuestion",
    "AnswerEvaluation",
    "FinalInterviewReport",
    "UsageRecord",
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


def _make_enum_type(allowed: tuple[str, ...], label: str):
    """Build an ``Annotated[str, ...]`` type restricted to ``allowed``."""

    def _check(value: str) -> str:
        if value not in allowed:
            raise ValueError(
                f"{label} must be one of {list(allowed)}; got {value!r}"
            )
        return value

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

# Enum-like scalar types (values validated against constants).
CareerLevel = _make_enum_type(constants.CAREER_LEVELS, "career_level")
InterviewerPersona = _make_enum_type(constants.INTERVIEWER_PERSONAS, "interviewer_persona")
Difficulty = _make_enum_type(constants.DIFFICULTY_LEVELS, "difficulty")
ResponseDetail = _make_enum_type(constants.RESPONSE_DETAIL_LEVELS, "response_detail")
PromptTechnique = _make_enum_type(constants.PROMPT_TECHNIQUES, "prompt_technique")
QuestionType = _make_enum_type(constants.INTERVIEW_TYPES, "question_type")
CostSource = _make_enum_type(constants.COST_SOURCES, "cost_source")
ApprovedModel = _make_enum_type(tuple(constants.APPROVED_MODELS), "model")

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


class InterviewStrategy(_StudioModel):
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


class InterviewQuestion(_StudioModel):
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
    difficulty: Difficulty = Field(description="Difficulty band for this question.")
    interviewer_intent: FreeText = Field(
        description="Concise note on what a strong answer should demonstrate "
        "(a rubric hint, not hidden reasoning)."
    )
    expected_answer_elements: StrList = Field(
        description="Key elements a strong answer would include."
    )


class AnswerEvaluation(_StudioModel):
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


class FinalInterviewReport(_StudioModel):
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
