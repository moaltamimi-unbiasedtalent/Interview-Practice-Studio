"""Load a tiny SYNTHETIC demo knowledge pack so a first-run user can try chat.

This exists purely so someone who has cloned the repo with no licensed source
data can still see grounded, cited retrieval working end to end. Everything it
loads is clearly-labelled synthetic demonstration content — it is NEVER
production-ready, is never confused with the real authoritative sources, and does
not touch any real dataset, the origins ledger, or the structured stores.

The pack is written to ``data/knowledge_demo/`` (git-ignored friendly) and
ingested into the vector store with a ``data_origin=synthetic_fixture`` tag and a
``source_url`` pointing back to this script, so citations render but can never be
mistaken for official figures.

Usage:
    python scripts/load_sample_knowledge.py            # persist to the vector store
    python scripts/load_sample_knowledge.py --in-memory  # dry run, no persistence
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.config import load_config  # noqa: E402
from src.copilot.embeddings import build_embedder  # noqa: E402
from src.copilot.ingestion import indexer  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402

DEMO_DIR = Path("data/knowledge_demo")
DEMO_URL = "synthetic://demo/load_sample_knowledge.py"

# Each entry becomes one demo markdown file. Content is generic across
# professions and deliberately illustrative — no real figures are asserted.
_DEMO_DOCS: dict[str, str] = {
    "interview_preparation_basics.md": """# Interview Preparation Basics (DEMO)

_This is synthetic demonstration content, not authoritative guidance._

Preparing for an interview generally involves three phases: researching the
role and organisation, rehearsing structured answers, and reviewing your own
examples. A common technique for behavioural questions is to structure answers
around a situation, the task, the action you took, and the result.

Practising out loud, timing your answers, and preparing two or three concrete
examples per competency tends to help candidates across professions — from
software and healthcare to trades, sales, and the public sector.
""",
    "competency_examples.md": """# Common Competencies (DEMO)

_This is synthetic demonstration content, not authoritative guidance._

Many roles assess a shared set of competencies: communication, problem solving,
collaboration, adaptability, and attention to detail. For each competency,
prepare a short story that shows the context, what you did, and the measurable
outcome. Tailor the examples to the seniority of the role.
""",
    "role_research_guide.md": """# Researching a Role (DEMO)

_This is synthetic demonstration content, not authoritative guidance._

When researching a role, look at the day-to-day responsibilities, the skills and
tools it typically requires, and how success is measured. Compare the job
description against your own experience to find the strongest matches and the
gaps worth addressing before the interview.
""",
}


def _write_demo_files() -> list[str]:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for name, text in _DEMO_DOCS.items():
        path = DEMO_DIR / name
        path.write_text(text, encoding="utf-8")
        paths.append(str(path))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the synthetic demo knowledge pack.")
    parser.add_argument("--in-memory", action="store_true",
                        help="ingest without persisting to the vector store")
    args = parser.parse_args(argv)

    print("=" * 68)
    print("DEMO KNOWLEDGE PACK — SYNTHETIC CONTENT ONLY (never production-ready)")
    print("=" * 68)

    paths = _write_demo_files()
    chunks, report = indexer.ingest_paths(paths)
    # Tag provenance so the UI/citations can never present this as official data.
    for chunk in chunks:
        chunk.metadata["data_origin"] = "synthetic_fixture"
        chunk.metadata["production_ready"] = False
        chunk.metadata.setdefault("source_url", DEMO_URL)
        chunk.metadata.setdefault("title", chunk.metadata.get("title", "Demo knowledge"))

    print(f"Prepared {len(chunks)} demo chunk(s) from {report.documents} file(s).")

    if args.in_memory:
        print("--in-memory: not persisted. Dry run complete.")
        return 0

    config = load_config()
    embedder = build_embedder(config)
    store = build_vector_store(config, embedder=embedder)
    store.add_chunks(chunks)
    print(f"Persisted {len(chunks)} demo chunk(s) to the vector store "
          f"(`{config.chroma_persist_dir}`).")
    print("Ask a question on the Career Intelligence chat page to try it.")
    print("Remove with: delete the vector store dir, or re-load real sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
