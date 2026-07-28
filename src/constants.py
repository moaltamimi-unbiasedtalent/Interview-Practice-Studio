"""Central constants for Interview Practice Studio.

Every approved model identifier and safe default setting lives here so that
all parts of the application read the same values. No other module should
hard-code model names or limits.
"""

# --- Application identity ---------------------------------------------------

APP_NAME = "Interview Practice Studio"
APP_TAGLINE = "Prepare for any role. Practise realistically. Improve every answer."

# --- Approved OpenRouter model identifiers ----------------------------------
# Only these three models may be used anywhere in the application.

DEFAULT_MODEL = "openai/gpt-5-mini"
LOW_COST_MODEL = "openai/gpt-5-nano"
HIGH_CAPABILITY_MODEL = "openai/gpt-5"

APPROVED_MODELS: dict[str, str] = {
    DEFAULT_MODEL: "Balanced default: good quality at moderate cost",
    LOW_COST_MODEL: "Lower-cost option for quick practice rounds",
    HIGH_CAPABILITY_MODEL: "Higher-capability option for detailed feedback",
}

# --- Safe generation defaults ------------------------------------------------
# Conservative values chosen so a fresh install behaves predictably.

DEFAULT_TEMPERATURE = 0.3
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 1.0

DEFAULT_MAX_OUTPUT_TOKENS = 1024
MIN_OUTPUT_TOKENS = 64
MAX_OUTPUT_TOKENS_LIMIT = 4096

# --- Input length limits ------------------------------------------------------
# Job descriptions, candidate backgrounds and answers are untrusted input.
# Hard character limits are the first line of defence against oversized or
# abusive payloads.

MAX_JOB_DESCRIPTION_CHARS = 8_000
MAX_CANDIDATE_BACKGROUND_CHARS = 4_000
MAX_ANSWER_CHARS = 6_000

# --- Enum-like allowed values ------------------------------------------------
# These tuples are the single source of truth for every "choose one of a fixed
# set" field in the domain models. They are deliberately profession-neutral: a
# software engineer, a nurse, an electrician and a teacher all map onto the
# same career levels, interview types and difficulty bands. Order is kept
# stable so it can drive UI dropdowns and produce readable error messages.

CAREER_LEVELS = (
    "internship",
    "entry",
    "junior",
    "mid",
    "senior",
    "lead",
    "principal",
    "manager",
    "director",
    "executive",
)

INTERVIEW_TYPES = (
    "screening",
    "behavioural",
    "technical",
    "situational",
    "competency",
    "case_study",
    "portfolio",
    "panel",
)

INTERVIEWER_PERSONAS = (
    "supportive",
    "neutral",
    "formal",
    "challenging",
)

DIFFICULTY_LEVELS = (
    "easy",
    "moderate",
    "hard",
)

RESPONSE_DETAIL_LEVELS = (
    "brief",
    "standard",
    "detailed",
)

# Five distinct prompting techniques (assignment requires at least five).
# None of these names implies exposing hidden chain-of-thought: feedback is
# always produced as concise, structured output, never a private monologue.
PROMPT_TECHNIQUES = (
    "zero_shot",
    "few_shot",
    "role_prompting",
    "structured_rubric",
    "self_refine",
)

# How a usage record's cost was obtained.
COST_SOURCES = (
    "reported",  # provided by OpenRouter in the response
    "calculated",  # derived locally from token counts
    "unavailable",  # neither available
)

# --- Interview sizing --------------------------------------------------------

MIN_QUESTIONS = 1
MAX_QUESTIONS = 20
DEFAULT_NUMBER_OF_QUESTIONS = 6

# --- Scoring bounds ----------------------------------------------------------
# Practice-feedback scores only — never treated as objective hiring decisions.

MIN_OVERALL_SCORE = 0
MAX_OVERALL_SCORE = 100
MIN_RUBRIC_SCORE = 1
MAX_RUBRIC_SCORE = 10

# --- Defensive text and list size limits -------------------------------------
# Bound the size of individual model fields so malformed or abusive structured
# output cannot balloon memory or the UI.

MAX_SHORT_TEXT_CHARS = 200
MAX_FREE_TEXT_CHARS = 4_000
MAX_LIST_ITEMS = 50

# --- Cost currency -----------------------------------------------------------
# OpenRouter reports spend in US dollars, so USD is the only supported
# currency for cost records in this project.

DEFAULT_CURRENCY = "USD"
SUPPORTED_CURRENCIES = ("USD",)
