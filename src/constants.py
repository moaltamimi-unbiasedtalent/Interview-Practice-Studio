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

# Models that do NOT accept a custom ``temperature`` (reasoning models run only at
# the provider default). Used to gate the temperature slider without a network
# call; live OpenRouter ``supported_parameters`` metadata overrides this when
# available (see ui_helpers.model_supports_temperature).
MODELS_WITHOUT_TEMPERATURE: set[str] = {
    "openai/gpt-5",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
}

DEFAULT_MAX_OUTPUT_TOKENS = 1024
# Floor for the output budget. Every use case produces a structured JSON object
# (a strategy or final report can be ~600-900 tokens plus a repair round), so a
# very small budget truncates the response mid-object and it cannot be parsed.
# 512 keeps short outputs (a single question/evaluation) working while removing
# the sub-512 range that cannot reliably hold a structured answer; the default
# (1024) is the recommended value for the larger strategy and report tasks.
MIN_OUTPUT_TOKENS = 512
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

# How many prior candidate answers to include, in full, when generating the
# next question. Previous questions (short) and compact evaluation summaries are
# always sent so the no-repeat rule and difficulty adaptation still work; only
# the full answer texts — the dominant token cost, up to MAX_ANSWER_CHARS each —
# are bounded to the most recent few so the prompt cannot grow without limit.
MAX_HISTORY_ANSWERS = 4

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

# --- Transient HTTP retry ----------------------------------------------------
# A single bounded retry at the HTTP boundary for errors that are likely
# temporary. Only the statuses below (plus timeouts and network failures) are
# retried; 4xx client errors (400/401/402/403), unsupported parameters, schema
# errors and security blocks are never retried. Kept at one retry so a single
# user action can never fan out into many billable requests.
MAX_TRANSIENT_RETRIES = 1
TRANSIENT_RETRY_STATUSES = (429, 502, 503)
# Backoff used when the response carries no Retry-After header. A small base
# delay plus jitter; the effective wait is capped so a hostile Retry-After
# cannot block the UI for long.
TRANSIENT_RETRY_BASE_DELAY_SECONDS = 0.5
TRANSIENT_RETRY_MAX_DELAY_SECONDS = 5.0

# --- Structured output -------------------------------------------------------
# When the selected model/provider enforces JSON Schema structured output, the
# request carries a strict schema generated from the target Pydantic model and
# no model-based JSON repair is used (a schema violation is then an exceptional
# provider issue, not an everyday formatting slip). Models without schema
# enforcement fall back to the defensive parser with one bounded repair.
STRUCTURED_OUTPUT_PARAMETER = "structured_outputs"
# Non-strict (JSON Schema unavailable) generation allows a single repair round.
MAX_REPAIR_ATTEMPTS = 1

# The connection-test request is deliberately small but must leave enough
# output budget for reasoning models (e.g. GPT-5) that spend tokens on internal
# reasoning before emitting visible content — an 8-token budget can otherwise
# return a valid response with no visible text.
CONNECTION_TEST_MAX_TOKENS = 256
CONNECTION_TEST_PROMPT = "Reply with exactly: OK"
# The connection test alone may retry once on an empty (no-text) generation.
CONNECTION_TEST_MAX_RETRIES = 1

# Reasoning models (e.g. GPT-5) spend output tokens on internal reasoning before
# producing visible content, which can exhaust the completion budget and return
# no text (finish_reason=length). For structured interview generation we request
# the smallest reasoning allocation so the token budget goes to the JSON answer.
# Sent only to models whose metadata advertises "reasoning"; omitted otherwise.
DEFAULT_REASONING_EFFORT = "minimal"

# --- Speech-to-text (voice answers) ------------------------------------------
# Recorded answers are transcribed by an external speech provider. Audio is
# validated before transcription and never persisted. Limits are deliberate: a
# hard 10-minute ceiling and a byte cap bound cost and abuse.
SPEECH_MAX_AUDIO_SECONDS = 600  # 10-minute hard maximum
SPEECH_MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB
SPEECH_TARGET_SAMPLE_RATE = 16_000  # 16 kHz is ideal for speech recognition
# Synchronous recognize handles only short (~1 min) inline audio. Longer
# recorded answers are sent via the streaming API, which supports minutes of
# audio inline (no Cloud Storage bucket needed). Below this threshold we use the
# simpler synchronous call.
SPEECH_STREAMING_THRESHOLD_SECONDS = 55
# Chunk size for feeding recorded audio to the streaming API (~64 KB).
SPEECH_STREAMING_CHUNK_BYTES = 64 * 1024
SPEECH_ALLOWED_MIME_TYPES = (
    "audio/wav",
    "audio/x-wav",
    "audio/wave",
    "audio/webm",
    "audio/ogg",
    "audio/mp4",
    "audio/mpeg",
)
# Provider, model and default routing for Google Cloud Speech-to-Text V2.
SPEECH_PROVIDER_GOOGLE = "google_chirp3"
SPEECH_MODEL_CHIRP3 = "chirp_3"
SPEECH_LOCATION_DEFAULT = "global"
# Language options offered in the UI (label, code). "auto" asks the provider to
# detect the language; the vocabulary is easy to extend later.
SPEECH_LANGUAGE_OPTIONS = (
    ("Automatic", "auto"),
    ("English", "en-US"),
    ("German", "de-DE"),
)
SPEECH_DEFAULT_LANGUAGE_CODES = ("en-US", "de-DE")
# Shown to the candidate near the recorder. Only true because audio is never
# written to disk or kept in session beyond the active request.
SPEECH_PRIVACY_NOTICE = (
    "Your recording is used to create the transcript. Raw audio is not saved by "
    "Interview Practice Studio."
)

# --- Live interview (Gemini Live, experimental) ------------------------------
# A real-time voice interface. OpenRouter stays the authoritative interview
# intelligence (questions, evaluation, Deep Dive, report); Gemini Live only
# speaks the canonical question and streams the candidate's audio/transcript.
LIVE_PROVIDER = "gemini_live"
# Default Gemini Live model; configurable so it can track the current release.
# Override with GEMINI_LIVE_MODEL if the id changes (it is not validated here —
# an invalid id only surfaces on a live session).
LIVE_INTERVIEW_MODEL = "gemini-3.1-flash-live-preview"
LIVE_AUDIO_SAMPLE_RATE = 16_000  # 16 kHz input, as Gemini Live expects
LIVE_AUDIO_OUTPUT_SAMPLE_RATE = 24_000  # Gemini streams 24 kHz output audio
# Small low-latency chunks (20-40 ms) rather than buffering seconds of audio.
LIVE_AUDIO_CHUNK_MS = 30
# Ephemeral tokens are short-lived; the browser only ever receives one of these.
LIVE_EPHEMERAL_TOKEN_TTL_SECONDS = 1_800  # 30 minutes
LIVE_NEW_SESSION_WINDOW_SECONDS = 60  # window to start a session with the token
# Bounded reconnect so a failing session can never loop forever.
LIVE_MAX_RECONNECTS = 3
LIVE_RECONNECT_BASE_DELAY_SECONDS = 1.0
LIVE_RECONNECT_MAX_DELAY_SECONDS = 8.0
LIVE_FALLBACK_MESSAGE = "Live interview is temporarily unavailable."

# --- Answer timing & delivery coaching ---------------------------------------
# Timing is guidance, never a hard limit and never a score input. Recommended
# durations are derived from a target answer word count and a professional
# speaking rate, so they vary by question type and difficulty rather than being
# an unexplained fixed number.
TARGET_SPEAKING_WPM = 130  # words per minute for a clear professional answer
MIN_RECOMMENDED_ANSWER_SECONDS = 30
MAX_RECOMMENDED_ANSWER_SECONDS = 300
# Live-timer coaching thresholds, as ratios of the recommended duration.
SOFT_WARNING_RATIO = 1.0  # at ~100% — "consider wrapping up"
HARD_GUIDANCE_RATIO = 1.2  # at ~120% — "bring it to a conclusion"
# A pause only "counts" once it is at least this long — small breaths are not
# conversational pauses.
MEANINGFUL_PAUSE_SECONDS = 1.2
# Aggregation thresholds: an answer is "substantially" over/under target beyond
# these ratios of the recommended duration.
OVER_TARGET_RATIO = 1.25
UNDER_TARGET_RATIO = 0.6

# Target answer word counts per question type. Chosen so recommended durations
# differ appropriately (a screening reply is short; a case study is long) — no
# question gets an identical, unexplained duration.
ANSWER_TARGET_WORDS: dict[str, int] = {
    "screening": 90,
    "behavioural": 220,
    "situational": 200,
    "competency": 220,
    "technical": 260,
    "case_study": 300,
    "portfolio": 240,
    "panel": 200,
    "leadership": 240,
    "culture_values": 160,
    "stakeholder": 220,
    "executive_board": 260,
}
DEFAULT_ANSWER_TARGET_WORDS = 180
DEEP_DIVE_TARGET_WORDS = 150  # deeper follow-ups should stay focused
# Difficulty scales the target length (harder questions warrant fuller answers).
DIFFICULTY_LENGTH_MULTIPLIER: dict[str, float] = {
    "easy": 0.85,
    "moderate": 1.0,
    "hard": 1.2,
}

# --- Visual engagement coach (optional, camera; local-only) ------------------
# A practice/coaching feature only. It NEVER decides whether a candidate is
# attentive, truthful or suitable, is NEVER part of any hiring score, and makes
# no psychological/medical/personality judgements. Camera is off by default;
# all frame processing happens locally in the browser and no video, screenshot,
# frame or biometric template is sent anywhere or stored — only aggregated
# coaching metrics are returned.
VISUAL_COACH_CALIBRATION_SECONDS = 3
# "Away" only counts as an extended period once it lasts at least this long.
VISUAL_EXTENDED_AWAY_SECONDS = 5.0
# Below these, feedback is withheld rather than invented (low confidence).
VISUAL_MIN_LANDMARK_CONFIDENCE = 0.5
VISUAL_MIN_FACE_PRESENT_PERCENT = 60.0
VISUAL_DISCLAIMER = (
    "Visual Engagement Coach analyses camera-facing behaviour locally on your "
    "device to help you practise video interviews. It does not determine whether "
    "you are attentive, truthful or suitable for a job."
)
VISUAL_LOW_CONFIDENCE_MESSAGE = (
    "Camera coaching confidence is too low for useful feedback."
)
VISUAL_STATUS_ACTIVE = "Camera coaching active"
# Allowed values for the clearly-named gaze proxy (never an "attention score").
GAZE_DIRECTION_PROXY_VALUES = (
    "toward_screen",
    "left",
    "right",
    "up",
    "down",
    "unknown",
)

# --- Candidate experience (avatar, modes, presentation) ----------------------
# The candidate-facing screen should feel like a remote interview, not a demo.
# None of these expose provider/model/token concepts to ordinary users.

# Interviewer avatar states (drive a tasteful animation, never fake lip-sync).
AVATAR_IDLE = "idle"
AVATAR_SPEAKING = "speaking"
AVATAR_LISTENING = "listening"
AVATAR_THINKING = "thinking"
AVATAR_STATES = (AVATAR_IDLE, AVATAR_SPEAKING, AVATAR_LISTENING, AVATAR_THINKING)

# Professional, neutral presentation per interviewer persona (no caricatures).
# label: friendly candidate-facing name; accent: a muted professional colour.
INTERVIEWER_PERSONA_PRESENTATION: dict[str, dict[str, str]] = {
    "supportive": {"label": "Friendly recruiter", "accent": "#2E7D32"},
    "neutral": {"label": "Hiring manager", "accent": "#1565C0"},
    "formal": {"label": "Formal interviewer", "accent": "#37474F"},
    "challenging": {"label": "Subject-matter expert", "accent": "#6A1B9A"},
    "sceptical_executive": {"label": "Executive", "accent": "#4E342E"},
    "fast_paced_panel": {"label": "Interview panel", "accent": "#00695C"},
}
DEFAULT_PERSONA_PRESENTATION = {"label": "Interviewer", "accent": "#1565C0"}

# Candidate-facing status text for waiting states (never a blank frozen screen).
STATUS_PREPARING_INTERVIEWER = "Preparing your interviewer…"
STATUS_LISTENING = "Listening…"
STATUS_PROCESSING_ANSWER = "Processing your answer…"
STATUS_PREPARING_FEEDBACK = "Preparing your feedback…"
STATUS_PREPARING_NEXT = "Preparing the next question…"
STATUS_RECONNECTING = "Reconnecting…"

# Friendly practice-mode cards (no technical jargon).
PRACTICE_MODE_CARDS = (
    {
        "id": "Type",
        "title": "💬 Text",
        "tagline": "Quiet, flexible practice.",
        "description": "Read each question and type your answer at your own pace.",
    },
    {
        "id": "Record",
        "title": "🎙️ Voice",
        "tagline": "Record spoken answers and get feedback.",
        "description": "Speak your answer aloud; we transcribe it and coach delivery.",
    },
    {
        "id": "Live",
        "title": "🎥 Live",
        "tagline": "Real-time AI interviewer with voice conversation.",
        "description": "A spoken, back-and-forth interview. Experimental.",
    },
)

# --- Accounts & persistence --------------------------------------------------
# Auth is optional for local development and required in production. The database
# URL selects SQLite for development or PostgreSQL for production via one mature
# ORM. Data is written to a local file by default; production overrides this.
DEFAULT_DATABASE_URL = "sqlite:///data/interview_studio.db"
# Retention: interview data is kept until the candidate deletes it. They can
# export everything and delete individual interviews or all of it (Settings).
DATA_RETENTION_NOTE = (
    "Your interviews are stored so you can review your progress. You can export "
    "your data or delete individual interviews or everything, at any time, from "
    "Settings. Camera video, audio and biometric data are never stored."
)

# --- Pricing -----------------------------------------------------------------
# Cost figures are computed with Decimal for precision, then rounded to this
# many decimal places for display/storage. Prices themselves are always read
# from OpenRouter model metadata, never hard-coded.

PRICING_DECIMAL_PLACES = 10
COST_ESTIMATE_DISCLAIMER = (
    "Estimated from current model pricing — not a final billed amount."
)
