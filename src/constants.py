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
