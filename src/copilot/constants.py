"""Central constants for Career Intelligence Copilot.

Models, endpoints, limits and defaults live here so no other module hard-codes
them. Namespaced under ``src.copilot`` to coexist with Interview Practice Studio.
"""

from __future__ import annotations

# --- Identity ----------------------------------------------------------------

APP_NAME = "Career Intelligence Copilot"
APP_TAGLINE = (
    "Grounded career guidance, job analysis and interview preparation using "
    "real evidence."
)

# --- OpenRouter (OpenAI-compatible) ------------------------------------------
# OpenRouter is used via its OpenAI-compatible API through LangChain.

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = "openai/gpt-5-mini"
APPROVED_MODELS: dict[str, str] = {
    "openai/gpt-5-mini": "Balanced default: good quality at moderate cost",
    "openai/gpt-5-nano": "Lower-cost option for quick tasks",
    "openai/gpt-5": "Higher-capability option for detailed analysis",
}

# Attribution headers (not secrets; safe to send/log).
OPENROUTER_APP_REFERER = (
    "https://github.com/moaltamimi-unbiasedtalent/Interview-Practice-Studio"
)
OPENROUTER_APP_TITLE = APP_NAME

# --- Generation defaults -----------------------------------------------------

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_OUTPUT_TOKENS = 1024
# Structured tool outputs (job analysis, question generation) enumerate many
# fields/items, so they need a larger budget than a chat reply — too small a cap
# truncates the JSON and raises LengthFinishReasonError.
STRUCTURED_MAX_OUTPUT_TOKENS = 4096

# Explicit timeouts (seconds). Fail fast on connect; tolerate slower generation.
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 60.0
# One bounded retry at the LLM boundary for transient errors.
LLM_MAX_RETRIES = 1

# --- Embeddings --------------------------------------------------------------
# OpenAI-compatible embeddings. Base URL is configurable because OpenRouter does
# not serve embeddings for every model; the provider is pluggable (see
# ``src/copilot/embeddings.py``). Two providers ship:
#   - "openai": OpenAI-compatible API (real semantic quality; needs a key).
#   - "local":  a dependency-free deterministic embedder (no key, offline) used
#               as a fallback and in tests. Lexical, not semantic.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_BASE_URL = "https://api.openai.com/v1"
# Provider selection. "auto" uses OpenAI when an embedding key is available and
# otherwise falls back to the local embedder so the app always runs.
DEFAULT_EMBEDDING_PROVIDER = "auto"
# Dimensions of the OpenAI text-embedding-3-small model.
OPENAI_EMBEDDING_DIMENSIONS = 1536
# Dimensions for the local deterministic embedder (independent of any provider).
LOCAL_EMBEDDING_DIMENSIONS = 512
LOCAL_EMBEDDING_MODEL = "local-hash-v1"

# --- Knowledge base / vector store paths (used from Phase 2) -----------------

DATA_DIR = "data"
RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
CHROMA_PERSIST_DIR = "data/chroma"

# --- Input limits (defensive; untrusted user input) --------------------------

MAX_QUERY_CHARS = 4_000
MAX_JOB_DESCRIPTION_CHARS = 12_000
MAX_CANDIDATE_BACKGROUND_CHARS = 8_000

# --- Knowledge base / ingestion ----------------------------------------------

# Document categories the knowledge base understands. Inferred from the raw
# subfolder name; anything else is "uncategorized".
KNOWN_DOCUMENT_TYPES = (
    "labour_market",
    "occupation",
    "skills",
    "career_guidance",
    "interview_guidance",
    "industry_report",
)
DEFAULT_DOCUMENT_TYPE = "uncategorized"

# Supported source formats (lower-case extensions).
SUPPORTED_EXTENSIONS = (".pdf", ".txt", ".md", ".markdown", ".csv")

# Recursive chunking. ~1000 chars keeps a chunk focused but self-contained; the
# overlap preserves context across boundaries. Sizes are in characters.
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150

# Length of the short, stable hex ids derived from content hashes (for dedup).
ID_HASH_LENGTH = 16

# Where the ingestion CLI writes processed chunks + a manifest (no embeddings).
PROCESSED_CHUNKS_FILE = "data/processed/chunks.jsonl"
PROCESSED_MANIFEST_FILE = "data/processed/manifest.json"

# --- Vector store / retrieval ------------------------------------------------

# Name of the Chroma collection holding the career knowledge base.
CHROMA_COLLECTION_NAME = "career_knowledge_base"
# Metadata keys that are safe to store on a vector (scalars only; Chroma rejects
# nested values). Everything else is dropped when indexing.
VECTOR_METADATA_KEYS = (
    "source_id",
    "chunk_index",
    "filename",
    "title",
    "document_type",
    "source",
    "page",
    "section",
)
# Default number of chunks to retrieve for a query.
DEFAULT_TOP_K = 5
# Character budget for the retrieved context assembled into the prompt. Keeps the
# request well within model limits and controls cost.
MAX_CONTEXT_CHARS = 6_000
# Batch size when embedding/indexing chunks.
EMBED_BATCH_SIZE = 64

# Sentinel the model is told to emit when the knowledge base lacks the evidence.
INSUFFICIENT_EVIDENCE_MESSAGE = (
    "The knowledge base does not contain enough evidence to answer that."
)

# --- Query translation -------------------------------------------------------

# Intents the query-understanding stage classifies. "smalltalk" and "other" are
# the non-knowledge intents; the rest are knowledge questions needing retrieval.
QUERY_INTENTS = (
    "factual_career",
    "role_research",
    "skill_research",
    "job_description_analysis",
    "candidate_comparison",
    "preparation_planning",
    "interview_preparation",
    "smalltalk",
    "other",
)
DEFAULT_INTENT = "other"
# Intents that do NOT require knowledge-base retrieval.
NO_RETRIEVAL_INTENTS = ("smalltalk",)

# Whitelist of metadata fields the translator may filter on, mapped to the set of
# allowed values (None = any scalar). This is what stops the LLM proposing
# arbitrary filters; only equality on these fields reaches the store.
ALLOWED_FILTER_FIELDS = {
    "document_type": set(KNOWN_DOCUMENT_TYPES),
}

# Number of alternate queries to request for broad questions (2–4 total variants
# including the rewritten query).
MAX_ALTERNATE_QUERIES = 3
# Reciprocal-rank-fusion constant (higher = flatter weighting of ranks).
RRF_K = 60

# --- Hybrid search -----------------------------------------------------------

# Retriever modes. Hybrid (vector + BM25) is the default; the others are kept for
# testing and evaluation.
RETRIEVAL_MODES = ("vector", "keyword", "hybrid")
DEFAULT_RETRIEVAL_MODE = "hybrid"

# RRF weights for hybrid fusion. Equal weights by default: neither channel is
# assumed better without evidence (see docs/hybrid_search.md and the evaluation
# baseline). Override via config if evaluation on your corpus justifies it.
HYBRID_VECTOR_WEIGHT = 1.0
HYBRID_KEYWORD_WEIGHT = 1.0
# Candidate pool each channel contributes before fusion (>= final top_k so a
# result strong in only one channel can still surface).
HYBRID_CANDIDATE_K = 10

# --- Domain tool calling -----------------------------------------------------

# Registered tool names (the ONLY functions the model may invoke). Anything else
# is rejected as unsupported — no arbitrary Python/shell/filesystem/network.
TOOL_JOB_ANALYZER = "job_description_analyzer"
TOOL_GAP_ANALYZER = "candidate_gap_analyzer"
TOOL_PREP_PLANNER = "preparation_plan_calculator"
TOOL_QUESTION_GENERATOR = "interview_question_generator"
REGISTERED_TOOLS = (
    TOOL_JOB_ANALYZER,
    TOOL_GAP_ANALYZER,
    TOOL_PREP_PLANNER,
    TOOL_QUESTION_GENERATOR,
)

# Severity weights used for deterministic time allocation and gap prioritisation.
SEVERITY_WEIGHTS = {"high": 3.0, "medium": 2.0, "low": 1.0}
SEVERITY_ORDER = ("high", "medium", "low")

# Default interview-question categories the generator may use.
QUESTION_CATEGORIES = (
    "behavioural",
    "situational",
    "competency",
    "technical",
    "leadership",
    "stakeholder",
    "executive",
    "culture_values",
)

# --- Security / prompt injection ---------------------------------------------

# Explicit input limits (characters). Over-limit input is flagged and bounded,
# never silently dropped.
MAX_UPLOAD_CHARS = 50_000

# Weighted-indicator thresholds for the deterministic injection scanner.
# A single high-weight indicator (3.0) blocks; a medium one (2.0) warns.
INJECTION_WARN_THRESHOLD = 2.0
INJECTION_BLOCK_THRESHOLD = 3.0

# Verdicts.
VERDICT_ALLOW = "allow"
VERDICT_WARN = "allow_with_warning"
VERDICT_BLOCK = "block"

# --- Knowledge architecture (multi-source) -----------------------------------

# Source types the knowledge base understands.
SOURCE_TYPES = (
    "occupation_taxonomy",
    "skills_taxonomy",
    "compensation_dataset",
    "labour_market_forecast",
    "competency_framework",
    "methodology",
    "industry_report",
)

# Source-authority ranking — retrieval/ranking metadata, NOT a truth score.
AUTHORITY_OFFICIAL = 1  # official / statistical (EC, ILO, O*NET, BLS, BA, ONS, Eurostat, Cedefop, NIST)
AUTHORITY_PUBLIC_FRAMEWORK = 2  # public/professional frameworks (Civil Service, DigComp, EQF)
AUTHORITY_INDUSTRY = 3  # reputable public industry research
AUTHORITY_LEVELS = (AUTHORITY_OFFICIAL, AUTHORITY_PUBLIC_FRAMEWORK, AUTHORITY_INDUSTRY)

# Retrieval lanes the router can select.
LANE_STRUCTURED_ROLE = "structured_role"
LANE_VECTOR = "vector"
LANE_COMPENSATION = "compensation"
LANE_FORECAST = "forecast"
LANE_MIXED = "mixed"
LANE_COMPETENCY = "competency"      # DigComp / digital capabilities
LANE_CYBERSECURITY = "cybersecurity"  # NICE work roles / cyber responsibilities
LANE_SHORTAGE = "shortage"          # labour/skills shortage data
LANE_OPENINGS = "openings"          # future job openings / replacement demand
LANE_SENIORITY = "seniority"        # behaviour/seniority frameworks
LANE_TRANSITION = "transition"      # career transition comparison
RETRIEVAL_LANES = (
    LANE_STRUCTURED_ROLE,
    LANE_VECTOR,
    LANE_COMPENSATION,
    LANE_FORECAST,
    LANE_MIXED,
    LANE_COMPETENCY,
    LANE_CYBERSECURITY,
    LANE_SHORTAGE,
    LANE_OPENINGS,
    LANE_SENIORITY,
    LANE_TRANSITION,
)

# Geographic source precedence: country-specific official data outranks generic
# international material when the question is country-specific.
COUNTRY_SOURCE_PRIORITY = {
    "DE": ["kldb", "berufenet", "ba_kompetenzkatalog", "ba_entgeltatlas", "esco", "isco08"],
    "US": ["onet", "bls_ooh", "bls_oews", "opm_occupational_groups", "isco08"],
    "UK": ["ons_ashe", "uk_civil_service_success_profiles", "uk_hr_success_profiles", "esco", "isco08"],
    "EU": ["esco", "esco_matrix", "eurostat_earnings", "cedefop_skills_forecast", "isco08"],
}

# Default local stores for the structured knowledge (git-ignored, like data/).
ROLE_DB_PATH = "data/knowledge/roles.db"
COMPENSATION_DB_PATH = "data/knowledge/compensation.db"
COMPETENCY_DB_PATH = "data/knowledge/competencies.db"
LABOUR_MARKET_DB_PATH = "data/knowledge/labour_market.db"
SOURCE_MANIFEST_PATH = "data/source_manifest.json"
# Generated runtime lifecycle status (derived; not hand-maintained).
SOURCE_STATUS_PATH = "data/source_status.json"

# --- Cost currency -----------------------------------------------------------

DEFAULT_CURRENCY = "USD"
