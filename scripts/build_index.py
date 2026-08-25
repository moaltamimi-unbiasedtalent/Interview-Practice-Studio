"""Embed processed chunks into the persistent vector store.

Reads ``data/processed/chunks.jsonl`` (produced by ``scripts/ingest.py``),
embeds each chunk and upserts it into the Chroma collection. Chunks whose stable
ids already exist are skipped, so re-running after adding a few documents only
embeds the new ones.

Usage:
  python scripts/build_index.py                 # index data/processed/chunks.jsonl
  python scripts/build_index.py --reset         # rebuild the collection from scratch
  python scripts/build_index.py --in-memory     # dry-run (no persistence)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.config import load_config  # noqa: E402
from src.copilot.embeddings import build_embedder  # noqa: E402
from src.copilot.models import DocumentChunk  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402


def _load_chunks(path: str) -> list[DocumentChunk]:
    chunks: list[DocumentChunk] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            chunks.append(DocumentChunk(**json.loads(line)))
    return chunks


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the vector index from processed chunks.")
    parser.add_argument("--chunks", default=constants.PROCESSED_CHUNKS_FILE)
    parser.add_argument("--reset", action="store_true", help="Rebuild from scratch.")
    parser.add_argument(
        "--in-memory", action="store_true", help="Do not persist (dry run)."
    )
    args = parser.parse_args(argv)

    if not Path(args.chunks).is_file():
        print(
            f"No processed chunks at {args.chunks}. Run scripts/ingest.py first "
            "(and add sources to data/raw/)."
        )
        return 0

    chunks = _load_chunks(args.chunks)
    if not chunks:
        print(f"{args.chunks} is empty; nothing to index.")
        return 0

    config = load_config()
    embedder = build_embedder(config)
    store = build_vector_store(config, embedder=embedder, in_memory=args.in_memory)

    if args.reset:
        store.reset()
        print("Collection reset.")

    print(
        f"Embedding provider: {embedder.provider} "
        f"(model={embedder.model}, dims={embedder.dimensions})"
    )
    if embedder.provider == "local":
        print(
            "NOTE: using the offline local embedder (lexical only). Set "
            "COPILOT_EMBEDDING_API_KEY for semantic OpenAI embeddings."
        )

    print(f"Indexing {len(chunks)} chunk(s)…")
    result = store.add_chunks(chunks)
    print("\n=== Index report ===")
    print(f"Added            : {result.added}")
    print(f"Skipped existing : {result.skipped_existing}")
    print(f"Total in store   : {result.total}")
    if not args.in_memory:
        print(f"\nPersisted to {config.chroma_persist_dir}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
