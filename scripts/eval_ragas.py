"""Optional RAGAS generation-quality evaluation CLI (never runs in normal CI).

Thin interface over the shared runner in
``src/copilot/evaluation/ragas_runner.py`` — the Streamlit Evaluation page uses
the same runner, so there is one evaluation implementation. Without evaluator
credentials this prints a clean NOT RUN and exits 0. A live run (``--live``)
generates answers over the PUBLIC held-out cases, scores them with RAGAS, and
writes a unique run directory for COMPLETE/PARTIAL runs; a FAILED run (no valid
scores) writes nothing and exits 2.

Usage:
    python scripts/eval_ragas.py                      # NOT RUN (no creds)
    python scripts/eval_ragas.py --live               # full live run
    python scripts/eval_ragas.py --live --limit 10    # small baseline
    python scripts/eval_ragas.py --live --category role_responsibilities
    python scripts/eval_ragas.py --require-live        # non-zero if it cannot run

Credentials (never printed):
    RAGAS_EVAL_API_KEY   (required for --live)   evaluator model key
    RAGAS_EVAL_BASE_URL, RAGAS_EVAL_MODEL, RAGAS_EVAL_EMBEDDING_MODEL  (optional)
    COPILOT_API_KEY / OpenRouter key             to generate answers (--live)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.evaluation import ragas_adapter as ra  # noqa: E402
from src.copilot.evaluation import ragas_runner as runner  # noqa: E402

_NOT_RUN = "RAGAS evaluation not run — evaluator credentials not configured."


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Optional RAGAS generation-quality evaluation.")
    parser.add_argument("--live", action="store_true", help="run the live evaluation")
    parser.add_argument("--require-live", action="store_true",
                        help="exit non-zero if the live run cannot proceed")
    parser.add_argument("--category", default=None, help="filter to one category")
    parser.add_argument("--limit", type=int, default=None, help="cap the number of cases")
    parser.add_argument("--output-dir", default=None, help="override the run directory")
    parser.add_argument("--allow-chat-fallback", action="store_true",
                        help="opt in to reuse the production chat key as the evaluator key")
    args = parser.parse_args(argv)

    def _skip(msg: str) -> int:
        print(msg)
        return 1 if args.require_live else 0

    if not args.live:
        print(_NOT_RUN)
        print("Run a live evaluation with:  python scripts/eval_ragas.py --live")
        return 1 if args.require_live else 0

    # Preconditions (safe checks; no secret values).
    if not ra.ragas_available():
        return _skip("RAGAS is not installed. Install with: pip install -e \".[evaluation]\"")
    evaluator = ra.evaluator_config_from_env(allow_chat_fallback=args.allow_chat_fallback)
    if evaluator is None:
        return _skip(_NOT_RUN)

    from src.copilot.config import load_config

    config = load_config()
    if not config.is_configured:
        return _skip("RAGAS live run needs a chat credential to generate answers "
                     "(COPILOT_API_KEY). Not configured — nothing was run.")

    print(f"Generating answers and scoring via the shared RAGAS runner "
          f"(limit={args.limit or 'all'}, category={args.category or 'all'})…")
    result = runner.run_live_ragas(
        config=config, evaluator_config=evaluator,
        limit=args.limit, category=args.category, output_dir=args.output_dir)

    # HARD STOP: an all-invalid run is never persisted as a normal result.
    if result.is_failed:
        print("RAGAS RUN FAILED — evaluator returned no valid scores.")
        print("No evaluation artifacts were written.")
        print("Check evaluator configuration: RAGAS_EVAL_API_KEY, RAGAS_EVAL_BASE_URL, "
              "RAGAS_EVAL_MODEL and RAGAS_EVAL_EMBEDDING_MODEL.")
        print(f"  Evaluator base URL: {'configured' if evaluator.base_url else 'default'}")
        print(f"  Evaluator model: {evaluator.model}")
        print(f"  Embedding model: {evaluator.embedding_model}")
        return 2

    print(f"Execution status: {result.status} · valid scores "
          f"{result.valid_score_count}/{result.expected_score_count} "
          f"({round(result.score_coverage * 100, 1)}% coverage)")
    if result.status == ra.STATUS_PARTIAL:
        print("PARTIAL run — some evaluator jobs returned no valid score; "
              "aggregates use only valid scores.")
    print(f"Wrote {result.output_directory}/results.json, results.csv, summary.md, "
          "run_config.json")
    for name, value in result.metrics.items():
        print(f"  {name}: {value if value is not None else 'n/a'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
