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

# Explicit timeouts (seconds). Fail fast on connect; tolerate slower generation.
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 60.0
# One bounded retry at the LLM boundary for transient errors.
LLM_MAX_RETRIES = 1

# --- Embeddings (configuration only in Phase 1; RAG built later) -------------
# OpenAI-compatible embeddings. Base URL is configurable because OpenRouter does
# not serve embeddings for every model; the provider is chosen in a later phase.
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
DEFAULT_EMBEDDING_BASE_URL = "https://api.openai.com/v1"

# --- Knowledge base / vector store paths (used from Phase 2) -----------------

DATA_DIR = "data"
RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"
CHROMA_PERSIST_DIR = "data/chroma"

# --- Input limits (defensive; untrusted user input) --------------------------

MAX_QUERY_CHARS = 4_000
MAX_JOB_DESCRIPTION_CHARS = 12_000
MAX_CANDIDATE_BACKGROUND_CHARS = 8_000

# --- Cost currency -----------------------------------------------------------

DEFAULT_CURRENCY = "USD"
