"""Index the local NARRATIVE sources (PDFs) into the vector store — local-first.

Uses the inventory to select only files whose intended storage target is the
vector lane (WEF, ESCO handbook, EQF, Cedefop/Eurostat reports, OPM handbooks,
Civil Service / HR success profiles, NICE methodology). Structured tables
(occupations, salaries, matrices) are NEVER vectorised. Files are read in place —
nothing under ``data/raw`` is moved, renamed or deleted.

Each chunk is tagged with its manifest ``source_id`` and public ``source_url`` so
chat citations link back to the authoritative source. A measured per-source chunk
count is written to ``data/knowledge/vector_sources.json`` for the Knowledge Base
lifecycle.

Usage:  python scripts/ingest_local_narrative.py [--in-memory] [--limit N]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.config import load_config  # noqa: E402
from src.copilot.embeddings import build_embedder  # noqa: E402
from src.copilot.ingestion import indexer  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402

INVENTORY = "data/source_inventory.json"
VECTOR_SOURCES = "data/knowledge/vector_sources.json"
RAW_DIR = "data/raw"


def _vector_files() -> list[dict]:
    with open(INVENTORY, encoding="utf-8") as handle:
        inv = json.load(handle)
    out = []
    for f in inv["files"]:
        if f["intended_storage_target"] == "vector" and f["extension"] in (".pdf", ".txt", ".md"):
            out.append(f)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Index local narrative PDFs into the vector store.")
    parser.add_argument("--in-memory", action="store_true", help="do not persist (dry run)")
    parser.add_argument("--limit", type=int, default=None, help="cap number of files (debug)")
    args = parser.parse_args(argv)

    if not os.path.isfile(INVENTORY):
        print(f"No inventory at {INVENTORY}. Run scripts/inventory_sources.py first.")
        return 1

    files = _vector_files()
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("No narrative files to index.")
        return 0

    entries = {e.source_id: e for e in km.load_manifest(constants.SOURCE_MANIFEST_PATH)}
    by_path = {os.path.join(RAW_DIR, f["relative_path"]): f for f in files}

    print(f"Indexing {len(files)} narrative file(s)…")
    chunks, report = indexer.ingest_paths(list(by_path.keys()))

    # Tag every chunk with manifest provenance so citations link back.
    per_source: dict[str, int] = {}
    for ch in chunks:
        meta = ch.metadata or {}
        src_path = meta.get("source") or meta.get("filename")
        # Match the chunk back to its originating file record.
        match = None
        for path, rec in by_path.items():
            if rec["filename"] == src_path or path.endswith(str(src_path)):
                match = rec
                break
        if match:
            sid = match["source_id"]
            entry = entries.get(sid)
            meta["manifest_source_id"] = sid
            if entry and entry.source_url:
                meta["source_url"] = entry.source_url
            if entry:
                meta.setdefault("title", entry.title)
            ch.metadata = meta
            per_source[sid] = per_source.get(sid, 0) + 1

    print(f"Produced {len(chunks)} chunk(s) across {len(per_source)} source(s).")

    if not args.in_memory:
        config = load_config()
        embedder = build_embedder(config)
        store = build_vector_store(config, embedder=embedder)
        result = store.add_chunks(chunks)
        print(f"Vector store: added {getattr(result, 'added', len(chunks))} chunk(s).")
        indexer.write_processed(chunks, report)
        os.makedirs(os.path.dirname(VECTOR_SOURCES), exist_ok=True)
        with open(VECTOR_SOURCES, "w", encoding="utf-8") as handle:
            json.dump({"generated": "on-demand", "chunks_by_source": per_source,
                       "total_chunks": len(chunks)}, handle, indent=2)
        print(f"Wrote {VECTOR_SOURCES}")

    for sid, n in sorted(per_source.items(), key=lambda kv: -kv[1]):
        print(f"  {sid:34} {n:5} chunks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
