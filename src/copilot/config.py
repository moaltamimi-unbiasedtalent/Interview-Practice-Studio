"""Configuration loading for Career Intelligence Copilot.

Secrets are resolved from Streamlit secrets first, then environment variables.
There is never a default API key: a missing key yields a controlled unconfigured
config (``is_configured == False``) rather than an exception, so the UI can show
a friendly message. The key is stored as ``SecretStr`` so it is masked if the
config is ever printed or logged.
"""

from __future__ import annotations

from dotenv import load_dotenv
from pydantic import BaseModel, SecretStr

from src.copilot import constants
from src.core import secrets as _secrets

__all__ = ["CopilotConfig", "load_config"]

API_KEY_NAME = "OPENROUTER_API_KEY"
BASE_URL_NAME = "OPENROUTER_BASE_URL"
MODEL_NAME = "COPILOT_MODEL"
EMBEDDING_MODEL_NAME = "COPILOT_EMBEDDING_MODEL"
EMBEDDING_BASE_URL_NAME = "COPILOT_EMBEDDING_BASE_URL"
EMBEDDING_KEY_NAME = "COPILOT_EMBEDDING_API_KEY"
EMBEDDING_PROVIDER_NAME = "COPILOT_EMBEDDING_PROVIDER"
CHROMA_DIR_NAME = "COPILOT_CHROMA_DIR"
DEBUG_NAME = "COPILOT_DEBUG"
RETRIEVAL_MODE_NAME = "COPILOT_RETRIEVAL_MODE"
HYBRID_VECTOR_WEIGHT_NAME = "COPILOT_HYBRID_VECTOR_WEIGHT"
HYBRID_KEYWORD_WEIGHT_NAME = "COPILOT_HYBRID_KEYWORD_WEIGHT"
HYBRID_ADAPTIVE_NAME = "COPILOT_HYBRID_ADAPTIVE"
RERANKER_PROVIDER_NAME = "COPILOT_RERANKER_PROVIDER"
RERANK_CANDIDATES_NAME = "COPILOT_RERANK_CANDIDATES"
RERANK_TOP_K_NAME = "COPILOT_RERANK_TOP_K"
CHUNKING_STRATEGY_NAME = "COPILOT_CHUNKING_STRATEGY"
QUALITY_MODE_NAME = "COPILOT_QUALITY_MODE"
QUERY_CACHE_TTL_NAME = "COPILOT_QUERY_CACHE_TTL_SECONDS"
QUERY_CACHE_MAX_NAME = "COPILOT_QUERY_CACHE_MAX_ENTRIES"
REVIEWER_MODE_NAME = "COPILOT_REVIEWER_MODE"


class CopilotConfig(BaseModel):
    """Runtime configuration. The API key is masked via ``SecretStr``."""

    api_key: SecretStr | None = None
    base_url: str = constants.OPENROUTER_BASE_URL
    default_model: str = constants.DEFAULT_MODEL

    # Embeddings (used from Phase 2; kept as config now). A separate optional key
    # allows a different embeddings provider from the chat provider.
    embedding_model: str = constants.DEFAULT_EMBEDDING_MODEL
    embedding_base_url: str = constants.DEFAULT_EMBEDDING_BASE_URL
    embedding_api_key: SecretStr | None = None
    # "auto" | "openai" | "local" — see constants.DEFAULT_EMBEDDING_PROVIDER.
    embedding_provider: str = constants.DEFAULT_EMBEDDING_PROVIDER

    # Vector store persistence.
    chroma_persist_dir: str = constants.CHROMA_PERSIST_DIR

    # Retrieval: "vector" | "keyword" | "hybrid" (default). Weights control the
    # RRF fusion of the two channels in hybrid mode.
    retrieval_mode: str = constants.DEFAULT_RETRIEVAL_MODE
    hybrid_vector_weight: float = constants.HYBRID_VECTOR_WEIGHT
    hybrid_keyword_weight: float = constants.HYBRID_KEYWORD_WEIGHT
    hybrid_adaptive: bool = constants.HYBRID_ADAPTIVE_DEFAULT

    # Optional reranker (OPT-1B) and chunking strategy (OPT-1C).
    reranker_provider: str = constants.DEFAULT_RERANKER_PROVIDER
    rerank_candidates: int = constants.RERANK_CANDIDATES
    rerank_top_k: int = constants.RERANK_TOP_K
    chunking_strategy: str = constants.DEFAULT_CHUNKING_STRATEGY

    # Quality/cost mode (OPT-4C) and session caches (OPT-4A).
    quality_mode: str = "balanced"   # quality | balanced | cheap
    query_cache_ttl_seconds: int = 300
    query_cache_max_entries: int = 256
    reviewer_mode: bool = False

    # Connection + development settings.
    connect_timeout_seconds: float = constants.CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: float = constants.READ_TIMEOUT_SECONDS
    app_referer: str = constants.OPENROUTER_APP_REFERER
    app_title: str = constants.OPENROUTER_APP_TITLE
    debug: bool = False

    @property
    def is_configured(self) -> bool:
        """True when a non-empty OpenRouter API key is available."""
        return (
            self.api_key is not None
            and self.api_key.get_secret_value().strip() != ""
        )

    @property
    def embedding_key(self) -> SecretStr | None:
        """Embedding key if set, else the OpenRouter key (same-provider default)."""
        return self.embedding_api_key or self.api_key


def _read_streamlit(name: str) -> str | None:
    """Read from Streamlit secrets (delegates to the shared reader)."""
    return _secrets.read_streamlit(name)


def _read_env(name: str) -> str | None:
    """Read from the environment (delegates to the shared reader)."""
    return _secrets.read_env(name)


def _read(name: str) -> str | None:
    """Streamlit secrets take precedence over environment variables."""
    return _read_streamlit(name) or _read_env(name)


def _read_bool(name: str, default: bool = False) -> bool:
    raw = _read(name)
    if raw is None:
        return default
    return raw.lower() in ("1", "true", "yes", "on")


def _read_float(name: str, default: float) -> float:
    raw = _read(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _read_mode(name: str, default: str) -> str:
    raw = _read(name)
    if raw and raw.lower() in constants.RETRIEVAL_MODES:
        return raw.lower()
    return default


def load_config() -> CopilotConfig:
    """Build the configuration from secrets/environment; never raises on a
    missing key."""
    load_dotenv(override=False)
    raw_key = _read(API_KEY_NAME)
    raw_embed_key = _read(EMBEDDING_KEY_NAME)

    # Hybrid weight validation (OPT-2): weights must be >= 0 and not both zero,
    # otherwise fusion would rank nothing — fall back to equal weights.
    vw = _read_float(HYBRID_VECTOR_WEIGHT_NAME, constants.HYBRID_VECTOR_WEIGHT)
    kw = _read_float(HYBRID_KEYWORD_WEIGHT_NAME, constants.HYBRID_KEYWORD_WEIGHT)
    if vw < 0 or kw < 0 or (vw == 0 and kw == 0):
        vw, kw = constants.HYBRID_VECTOR_WEIGHT, constants.HYBRID_KEYWORD_WEIGHT

    def _int(name, default):
        raw = _read(name)
        try:
            return int(raw) if raw is not None else default
        except ValueError:
            return default

    quality = (_read(QUALITY_MODE_NAME) or "balanced").lower()
    if quality not in ("quality", "balanced", "cheap"):
        quality = "balanced"
    reranker = (_read(RERANKER_PROVIDER_NAME) or constants.DEFAULT_RERANKER_PROVIDER).lower()
    if reranker not in ("none", "llm"):
        reranker = "none"
    chunking = (_read(CHUNKING_STRATEGY_NAME) or constants.DEFAULT_CHUNKING_STRATEGY).lower()
    if chunking not in ("baseline", "section"):
        chunking = constants.DEFAULT_CHUNKING_STRATEGY

    return CopilotConfig(
        api_key=SecretStr(raw_key) if raw_key else None,
        base_url=_read(BASE_URL_NAME) or constants.OPENROUTER_BASE_URL,
        default_model=_read(MODEL_NAME) or constants.DEFAULT_MODEL,
        embedding_model=_read(EMBEDDING_MODEL_NAME)
        or constants.DEFAULT_EMBEDDING_MODEL,
        embedding_base_url=_read(EMBEDDING_BASE_URL_NAME)
        or constants.DEFAULT_EMBEDDING_BASE_URL,
        embedding_api_key=SecretStr(raw_embed_key) if raw_embed_key else None,
        embedding_provider=(
            _read(EMBEDDING_PROVIDER_NAME) or constants.DEFAULT_EMBEDDING_PROVIDER
        ).lower(),
        chroma_persist_dir=_read(CHROMA_DIR_NAME) or constants.CHROMA_PERSIST_DIR,
        retrieval_mode=_read_mode(RETRIEVAL_MODE_NAME, constants.DEFAULT_RETRIEVAL_MODE),
        hybrid_vector_weight=vw,
        hybrid_keyword_weight=kw,
        hybrid_adaptive=_read_bool(HYBRID_ADAPTIVE_NAME, default=constants.HYBRID_ADAPTIVE_DEFAULT),
        reranker_provider=reranker,
        rerank_candidates=_int(RERANK_CANDIDATES_NAME, constants.RERANK_CANDIDATES),
        rerank_top_k=_int(RERANK_TOP_K_NAME, constants.RERANK_TOP_K),
        chunking_strategy=chunking,
        quality_mode=quality,
        query_cache_ttl_seconds=_int(QUERY_CACHE_TTL_NAME, 300),
        query_cache_max_entries=_int(QUERY_CACHE_MAX_NAME, 256),
        reviewer_mode=_read_bool(REVIEWER_MODE_NAME, default=False),
        debug=_read_bool(DEBUG_NAME, default=False),
    )
