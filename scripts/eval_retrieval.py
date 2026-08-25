"""Compare vector / keyword / hybrid retrieval on a set of probes.

Reports lexical proxy metrics only (see src/copilot/evaluation/retrieval_eval.py
and docs/hybrid_search.md). It does NOT prove one mode is better overall —
relevance labels would be needed for that.

Usage:
  python scripts/eval_retrieval.py
  python scripts/eval_retrieval.py --probes data/eval/retrieval_probes.json --top-k 5
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.config import load_config  # noqa: E402
from src.copilot.evaluation import evaluate_modes, load_probes  # noqa: E402
from src.copilot.retrieval import build_retriever  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402

_DEFAULT_PROBES = "data/eval/retrieval_probes.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare retrieval modes on probes.")
    parser.add_argument("--probes", default=_DEFAULT_PROBES)
    parser.add_argument("--top-k", type=int, default=constants.DEFAULT_TOP_K)
    args = parser.parse_args(argv)

    if not Path(args.probes).is_file():
        print(f"No probes file at {args.probes}.")
        return 0

    config = load_config()
    store = build_vector_store(config)
    if store.count() == 0:
        print(
            "The vector store is empty. Ingest and index a knowledge base first "
            "(scripts/ingest.py, scripts/build_index.py) before evaluating."
        )
        return 0

    probes = load_probes(args.probes)
    # One shared store; each mode builds its retriever over the same chunks.
    retrievers = {
        mode: build_retriever(config, mode=mode, store=store)
        for mode in constants.RETRIEVAL_MODES
    }
    metrics = evaluate_modes(retrievers, probes, top_k=args.top_k)

    print(f"\nRetrieval comparison over {len(probes)} probe(s), top_k={args.top_k}")
    print("(lexical proxy metrics — NOT proof of overall relevance)\n")
    header = f"{'mode':<10} {'term_recall@k':>14} {'coverage':>10} {'avg_results':>12}"
    print(header)
    print("-" * len(header))
    for mode in constants.RETRIEVAL_MODES:
        m = metrics[mode]
        print(
            f"{m.mode:<10} {m.term_recall_at_k:>14.3f} "
            f"{m.coverage:>10.3f} {m.avg_results:>12.2f}"
        )
    print(
        "\nInterpretation: BM25/hybrid usually help exact-term probes (Python, SAP, "
        "SQL, ISO 27001). Draw conclusions only from your own corpus + labels."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
