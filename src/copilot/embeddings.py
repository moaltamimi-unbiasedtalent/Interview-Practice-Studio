"""Embedding abstraction for Career Intelligence Copilot.

The rest of the system depends on the small :class:`BaseEmbedder` interface, not
on any one provider, so the embedding backend can change without touching
retrieval, the vector store or the RAG chain.

Two providers ship:

* :class:`OpenAIEmbedder` — OpenAI-compatible embeddings API (real semantic
  quality). Needs an embedding API key; the base URL is configurable because
  OpenRouter does not serve embeddings for every model.
* :class:`LocalHashEmbedder` — a dependency-free, deterministic embedder used as
  an offline fallback and in tests. It hashes tokens into a fixed-width vector
  (a lexical signal, not true semantics), so the app always runs even with no
  key and no network. Its limits are documented in ``docs/rag.md``.

:func:`build_embedder` picks a provider from configuration.
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from typing import Any

from src.copilot import constants
from src.copilot.config import CopilotConfig

__all__ = [
    "BaseEmbedder",
    "OpenAIEmbedder",
    "LocalHashEmbedder",
    "build_embedder",
]


class BaseEmbedder(ABC):
    """Minimal embedding interface the rest of the app depends on."""

    #: Provider label, e.g. "openai" or "local".
    provider: str
    #: Model identifier for provenance/logging.
    model: str
    #: Vector dimensionality.
    dimensions: int

    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents (index time)."""

    @abstractmethod
    def embed_query(self, text: str) -> list[float]:
        """Embed a single query (retrieval time)."""

    def describe(self) -> dict[str, Any]:
        """Non-secret description for the UI / manifests."""
        return {
            "provider": self.provider,
            "model": self.model,
            "dimensions": self.dimensions,
        }


# --- Local, dependency-free fallback -----------------------------------------

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class LocalHashEmbedder(BaseEmbedder):
    """Deterministic hashing embedder — no dependencies, no network.

    Each token is hashed into a bucket and weighted by a sublinear term count;
    the resulting vector is L2-normalised so cosine similarity is meaningful.
    This captures lexical overlap only, but makes the whole RAG pipeline runnable
    and fully testable offline. Real semantic retrieval uses :class:`OpenAIEmbedder`.
    """

    provider = "local"

    def __init__(self, dimensions: int = constants.LOCAL_EMBEDDING_DIMENSIONS) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions
        self.model = constants.LOCAL_EMBEDDING_MODEL

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        counts: dict[str, int] = {}
        for token in _TOKEN_RE.findall(text.lower()):
            counts[token] = counts.get(token, 0) + 1
        for token, count in counts.items():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            # Sign bit spreads tokens across the space so overlaps don't all add.
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign * (1.0 + math.log(count))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector  # empty/whitespace text -> zero vector
        return [value / norm for value in vector]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed_one(text)


# --- OpenAI-compatible provider ----------------------------------------------


class OpenAIEmbedder(BaseEmbedder):
    """Embeddings via an OpenAI-compatible API (real semantic quality).

    Wraps ``langchain_openai.OpenAIEmbeddings`` (lazily imported). The key is
    read from ``SecretStr`` only at construction and handed straight to the
    client — never logged. ``embeddings_cls`` can be injected in tests.
    """

    provider = "openai"

    def __init__(
        self,
        config: CopilotConfig,
        *,
        embeddings_cls: Any | None = None,
    ) -> None:
        key = config.embedding_key
        if key is None or not key.get_secret_value().strip():
            raise ValueError(
                "No embedding API key configured. Set COPILOT_EMBEDDING_API_KEY "
                "(or OPENROUTER_API_KEY) to use the OpenAI embedding provider, or "
                "set COPILOT_EMBEDDING_PROVIDER=local for the offline embedder."
            )
        self.model = config.embedding_model
        self.dimensions = constants.OPENAI_EMBEDDING_DIMENSIONS

        if embeddings_cls is None:
            try:
                from langchain_openai import OpenAIEmbeddings as embeddings_cls  # type: ignore
            except ImportError as exc:  # pragma: no cover - optional dep
                raise ValueError(
                    "langchain-openai is not installed; cannot use the OpenAI "
                    "embedding provider."
                ) from exc

        self._client = embeddings_cls(
            model=self.model,
            api_key=key.get_secret_value(),
            base_url=config.embedding_base_url,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(list(texts))

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


def build_embedder(
    config: CopilotConfig,
    *,
    embeddings_cls: Any | None = None,
) -> BaseEmbedder:
    """Return an embedder chosen from ``config.embedding_provider``.

    - ``"local"``: always the offline hashing embedder.
    - ``"openai"``: the OpenAI-compatible embedder (raises if no key).
    - ``"auto"`` (default): OpenAI only when a DEDICATED embedding key
      (``COPILOT_EMBEDDING_API_KEY``) is set, otherwise the local embedder. The
      chat ``OPENROUTER_API_KEY`` is NOT used as an embedding key: OpenRouter does
      not serve OpenAI's embeddings endpoint, so falling back to it produces 401s.
      Set ``COPILOT_EMBEDDING_PROVIDER=openai`` to force the OpenAI provider.
    """
    provider = (config.embedding_provider or "auto").lower()
    if provider == "local":
        return LocalHashEmbedder()
    if provider == "openai":
        return OpenAIEmbedder(config, embeddings_cls=embeddings_cls)
    # auto: only use OpenAI embeddings with a purpose-set embedding key.
    key = config.embedding_api_key
    if key is not None and key.get_secret_value().strip():
        return OpenAIEmbedder(config, embeddings_cls=embeddings_cls)
    return LocalHashEmbedder()
