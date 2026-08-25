"""Vector store for Career Intelligence Copilot.

Two interchangeable backends implement the same :class:`BaseVectorStore`
interface so retrieval never depends on a specific store:

* :class:`ChromaStore` — a *persistent* Chroma collection (the real store).
* :class:`InMemoryVectorStore` — a pure-Python cosine store with no
  dependencies, used as a fallback when Chroma is not installed and as the
  backend in tests.

Both store the embedding, chunk text, sanitised metadata and the stable chunk id,
and both skip re-indexing chunks whose ids are already present, so re-running the
indexer over unchanged content is cheap.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.embeddings import BaseEmbedder, build_embedder
from src.copilot.models import DocumentChunk

__all__ = [
    "VectorHit",
    "IndexResult",
    "BaseVectorStore",
    "ChromaStore",
    "InMemoryVectorStore",
    "build_vector_store",
    "sanitize_metadata",
]


@dataclass
class VectorHit:
    """One raw hit from the vector store (before mapping to a RetrievalResult)."""

    chunk_id: str
    doc_id: str
    text: str
    metadata: dict
    score: float  # cosine similarity, higher is better


@dataclass
class IndexResult:
    """Outcome of an indexing call."""

    added: int = 0
    skipped_existing: int = 0
    total: int = 0

    def as_dict(self) -> dict:
        return {"added": self.added, "skipped_existing": self.skipped_existing, "total": self.total}


def sanitize_metadata(metadata: dict, *, doc_id: str) -> dict:
    """Keep only known scalar metadata (Chroma rejects nested values)."""
    clean: dict = {"doc_id": doc_id}
    for key in constants.VECTOR_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, (str, int, float, bool)):
            clean[key] = value
    return clean


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _matches(metadata: dict, filters: dict | None) -> bool:
    if not filters:
        return True
    return all(metadata.get(key) == value for key, value in filters.items())


class BaseVectorStore(ABC):
    """Shared store interface. Holds the embedder used for index + query."""

    embedder: BaseEmbedder

    @abstractmethod
    def add_chunks(self, chunks: Sequence[DocumentChunk]) -> IndexResult:
        ...

    @abstractmethod
    def query(
        self, text: str, *, top_k: int, filters: dict | None = None
    ) -> list[VectorHit]:
        ...

    @abstractmethod
    def count(self) -> int:
        ...

    @abstractmethod
    def reset(self) -> None:
        ...


class InMemoryVectorStore(BaseVectorStore):
    """A dependency-free cosine store (fallback + tests)."""

    def __init__(self, embedder: BaseEmbedder) -> None:
        self.embedder = embedder
        self._items: dict[str, dict] = {}

    def add_chunks(self, chunks: Sequence[DocumentChunk]) -> IndexResult:
        new = [c for c in chunks if c.chunk_id not in self._items]
        skipped = len(chunks) - len(new)
        if new:
            vectors = self.embedder.embed_documents([c.text for c in new])
            for chunk, vector in zip(new, vectors):
                self._items[chunk.chunk_id] = {
                    "doc_id": chunk.doc_id,
                    "text": chunk.text,
                    "metadata": sanitize_metadata(chunk.metadata, doc_id=chunk.doc_id),
                    "vector": vector,
                }
        return IndexResult(added=len(new), skipped_existing=skipped, total=len(self._items))

    def query(
        self, text: str, *, top_k: int, filters: dict | None = None
    ) -> list[VectorHit]:
        if not self._items or top_k <= 0:
            return []
        qvec = self.embedder.embed_query(text)
        scored: list[VectorHit] = []
        for chunk_id, item in self._items.items():
            if not _matches(item["metadata"], filters):
                continue
            scored.append(
                VectorHit(
                    chunk_id=chunk_id,
                    doc_id=item["doc_id"],
                    text=item["text"],
                    metadata=dict(item["metadata"]),
                    score=_cosine(qvec, item["vector"]),
                )
            )
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:top_k]

    def count(self) -> int:
        return len(self._items)

    def reset(self) -> None:
        self._items.clear()


class ChromaStore(BaseVectorStore):
    """A persistent Chroma-backed vector store (cosine space)."""

    def __init__(
        self,
        embedder: BaseEmbedder,
        *,
        persist_dir: str = constants.CHROMA_PERSIST_DIR,
        collection_name: str = constants.CHROMA_COLLECTION_NAME,
    ) -> None:
        import logging

        import chromadb  # local import: optional dependency
        from chromadb.config import Settings

        # Chroma's telemetry client logs noisy ERRORs on some posthog versions
        # even when disabled; silence it (nothing leaves the machine either way).
        logging.getLogger("chromadb.telemetry").setLevel(logging.CRITICAL)

        self.embedder = embedder
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        # Local-only telemetry is disabled: nothing about queries leaves the machine.
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def _existing_ids(self, ids: list[str]) -> set[str]:
        if not ids:
            return set()
        got = self._collection.get(ids=ids, include=[])
        return set(got.get("ids", []))

    def add_chunks(self, chunks: Sequence[DocumentChunk]) -> IndexResult:
        chunks = list(chunks)
        if not chunks:
            return IndexResult(total=self.count())
        existing = self._existing_ids([c.chunk_id for c in chunks])
        new = [c for c in chunks if c.chunk_id not in existing]
        skipped = len(chunks) - len(new)
        added = 0
        # Embed + add in batches to bound memory and request size.
        batch = constants.EMBED_BATCH_SIZE
        for start in range(0, len(new), batch):
            group = new[start : start + batch]
            vectors = self.embedder.embed_documents([c.text for c in group])
            self._collection.add(
                ids=[c.chunk_id for c in group],
                documents=[c.text for c in group],
                metadatas=[
                    sanitize_metadata(c.metadata, doc_id=c.doc_id) for c in group
                ],
                embeddings=vectors,
            )
            added += len(group)
        return IndexResult(added=added, skipped_existing=skipped, total=self.count())

    @staticmethod
    def _where(filters: dict | None) -> dict | None:
        if not filters:
            return None
        conditions = [{key: value} for key, value in filters.items()]
        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def query(
        self, text: str, *, top_k: int, filters: dict | None = None
    ) -> list[VectorHit]:
        if top_k <= 0 or self.count() == 0:
            return []
        qvec = self.embedder.embed_query(text)
        result = self._collection.query(
            query_embeddings=[qvec],
            n_results=min(top_k, self.count()),
            where=self._where(filters),
            include=["documents", "metadatas", "distances"],
        )
        ids = (result.get("ids") or [[]])[0]
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        hits: list[VectorHit] = []
        for chunk_id, text_, metadata, distance in zip(
            ids, documents, metadatas, distances
        ):
            metadata = dict(metadata or {})
            hits.append(
                VectorHit(
                    chunk_id=chunk_id,
                    doc_id=metadata.get("doc_id", ""),
                    text=text_,
                    metadata=metadata,
                    score=1.0 - float(distance),  # cosine distance -> similarity
                )
            )
        return hits

    def count(self) -> int:
        return self._collection.count()

    def reset(self) -> None:
        self._client.delete_collection(self.collection_name)
        self._collection = self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )


def _chroma_available() -> bool:
    try:
        import chromadb  # noqa: F401

        return True
    except ImportError:
        return False


def build_vector_store(
    config: CopilotConfig,
    *,
    embedder: BaseEmbedder | None = None,
    in_memory: bool = False,
) -> BaseVectorStore:
    """Build a vector store; Chroma when available unless ``in_memory`` is set."""
    embedder = embedder or build_embedder(config)
    if in_memory or not _chroma_available():
        return InMemoryVectorStore(embedder)
    return ChromaStore(embedder, persist_dir=config.chroma_persist_dir)
