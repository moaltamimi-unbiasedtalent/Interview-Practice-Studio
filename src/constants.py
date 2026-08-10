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
MAX_TARGET_ROLE_CHARS = 200
MAX_INDUSTRY_CHARS = 200
MAX_COMPANY_CONTEXT_CHARS = 4_000
MAX_INSTRUCTION_CHARS = 2_000

# --- Security guard thresholds -----------------------------------------------
# The security guard (src/security.py) is a deterministic, best-effort layer,
# not a perfect or production-grade filter. It scores untrusted text against
# several weighted indicators and maps the total to one of three outcomes.
# A single strong indicator (weight >= BLOCK) blocks; milder signals warn.

INJECTION_WARN_SCORE = 2  # score at/above this warns
INJECTION_BLOCK_SCORE = 4  # score at/above this blocks

# Maximum size of a model response the output guard will accept before
# treating it as anomalous.
MAX_MODEL_OUTPUT_CHARS = 20_000

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
    "leadership",
    "culture_values",
    "stakeholder",
    "executive_board",
)

INTERVIEWER_PERSONAS = (
    "supportive",
    "neutral",
    "formal",
    "challenging",
    "sceptical_executive",
    "fast_paced_panel",
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
# These are the stable technique IDs used by src/prompts.py and the prompt
# registry. None of these names implies exposing hidden chain-of-thought:
# feedback is always produced as concise, structured output, never a private
# monologue.
PROMPT_TECHNIQUES = (
    "zero_shot",  # Zero-shot instruction
    "role_persona",  # Role and persona prompting
    "few_shot",  # Few-shot prompting
    "structured_procedure",  # Structured analytical procedure
    "rubric_json",  # Rubric-constrained structured-output prompting
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

# --- Interview Deep Dive (branching) -----------------------------------------
# A candidate may branch from an evaluated answer to explore the same topic in
# more depth, then return to the main interview. Branch modes are the kinds of
# deeper exploration offered; depth is bounded so the exploration can never
# become an unlimited recursive conversation.

BRANCH_MODES = (
    "deepen_reasoning",  # why / how / what logic supports the answer
    "challenge_assumptions",  # what assumptions; what would invalidate them
    "explore_evidence",  # what data/examples/metrics support it
    "explore_tradeoffs",  # alternatives, risks, priorities
    "go_technical",  # domain methodology, tools, calculations
    "executive_challenge",  # senior/board-style challenge of the recommendation
)
DEFAULT_BRANCH_MODE = "deepen_reasoning"
MAX_BRANCH_DEPTH = 2

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

# --- OpenRouter API ----------------------------------------------------------
# The single OpenRouter host and the two endpoints this project uses. Kept here
# so no module hard-codes a URL.

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_CHAT_COMPLETIONS_PATH = "/chat/completions"
OPENROUTER_MODELS_PATH = "/models"

# OpenRouter uses these optional headers for attribution/ranking. They are not
# secrets and are safe to send and to log.
OPENROUTER_APP_REFERER = (
    "https://github.com/moaltamimi-unbiasedtalent/Interview-Practice-Studio"
)
OPENROUTER_APP_TITLE = APP_NAME

# Explicit timeouts (seconds). A short connect timeout fails fast on network
# problems; a longer read timeout tolerates slower model responses.
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 60.0

# The connection-test request is deliberately tiny.
CONNECTION_TEST_MAX_TOKENS = 8

# --- Pricing -----------------------------------------------------------------
# Cost figures are computed with Decimal for precision, then rounded to this
# many decimal places for display/storage. Prices themselves are always read
# from OpenRouter model metadata, never hard-coded.

PRICING_DECIMAL_PLACES = 10
COST_ESTIMATE_DISCLAIMER = (
    "Estimated from current model pricing — not a final billed amount."
)
