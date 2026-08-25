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

# --- Cost currency -----------------------------------------------------------

DEFAULT_CURRENCY = "USD"
