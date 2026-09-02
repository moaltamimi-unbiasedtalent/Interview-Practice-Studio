"""Optional RAGAS generation-quality evaluation CLI (never runs in normal CI).

Without evaluator credentials it prints a clean NOT RUN and exits 0. A live run
(``--live``) generates answers by running Career Intelligence over the PUBLIC
held-out cases, then scores them with RAGAS. Results go to a unique directory
under ``evaluations/ragas/runs/`` and never overwrite prior runs.

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
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.evaluation import ragas_adapter as ra  # noqa: E402

CASES = "evaluations/ragas/cases.json"
RUNS_DIR = Path("evaluations/ragas/runs")
_NOT_RUN = "RAGAS evaluation not run — evaluator credentials not configured."


def _git_sha() -> str | None:
    import subprocess

    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001 - git optional
        return None


def _build_service(config):
    from src.copilot.embeddings import build_embedder
    from src.copilot.knowledge.retrieval import build_default_coordinator
    from src.copilot.retrieval import build_retriever
    from src.copilot.service import CareerIntelligenceService
    from src.copilot.vectorstore import build_vector_store

    store = build_vector_store(config, embedder=build_embedder(config))
    retriever = build_retriever(config, mode=config.retrieval_mode, store=store)
    coordinator = build_default_coordinator(config)
    return CareerIntelligenceService(
        config=config, retriever=retriever, knowledge_coordinator=coordinator)


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

    # Load + filter PUBLIC cases (questions only; answers generated live).
    question_cases = ra.load_cases(CASES)
    if args.category:
        question_cases = [c for c in question_cases
                          if c.metadata.get("category") == args.category]
    if args.limit:
        question_cases = question_cases[: args.limit]
    if not question_cases:
        return _skip("No matching cases to evaluate.")

    print(f"Generating answers for {len(question_cases)} case(s) via Career Intelligence…")
    service = _build_service(config)
    eval_cases = []
    for qc in question_cases:
        result = service.answer(qc.question)
        eval_cases.append(ra.case_from_service_result(
            qc.case_id, qc.question, result,
            category=qc.metadata.get("category"), reference=qc.reference))

    print("Scoring with RAGAS (LLM evaluator)…")
    run = ra.run_ragas(eval_cases, config=evaluator)

    # HARD STOP before any artifact is created: an all-invalid run (e.g. the
    # evaluator failed to authenticate and every metric came back NaN) must NOT
    # be persisted as a normal evaluation result.
    if not ra.has_usable_scores(run):
        print("RAGAS RUN FAILED — evaluator returned no valid scores.")
        print("No evaluation artifacts were written.")
        print("Check evaluator configuration: RAGAS_EVAL_API_KEY, RAGAS_EVAL_BASE_URL, "
              "RAGAS_EVAL_MODEL and RAGAS_EVAL_EMBEDDING_MODEL.")
        print(f"  Evaluator base URL: {'configured' if evaluator.base_url else 'default'}")
        print(f"  Evaluator model: {evaluator.model}")
        print(f"  Embedding model: {evaluator.embedding_model}")
        return 2

    # COMPLETE / PARTIAL: create the unique run directory and write artifacts.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out = Path(args.output_dir) if args.output_dir else RUNS_DIR / stamp
    out.mkdir(parents=True, exist_ok=True)
    _write_artifacts(out, run, evaluator, stamp)
    print(f"Execution status: {run['status']} · valid scores "
          f"{run['valid_score_count']}/{run['expected_score_count']} "
          f"({round(run['score_coverage'] * 100, 1)}% coverage)")
    if run["status"] == ra.STATUS_PARTIAL:
        print("PARTIAL run — some evaluator jobs returned no valid score; "
              "aggregates use only valid scores.")
    print(f"Wrote {out}/results.json, results.csv, summary.md, run_config.json")
    for name, value in run["metrics"].items():
        print(f"  {name}: {value if value is not None else 'n/a'}")
    return 0


def _write_artifacts(out: Path, run: dict, evaluator, stamp: str) -> None:
    import csv

    try:
        import ragas
        ragas_version = getattr(ragas, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        ragas_version = "unknown"

    run_config = {
        "timestamp": stamp,
        "ragas_version": ragas_version,
        "status": run["status"],
        "case_count": run["case_count"],
        "referenced_case_count": run["referenced_case_count"],
        "context_recall_run": run["context_recall_run"],
        "valid_score_count": run["valid_score_count"],
        "expected_score_count": run["expected_score_count"],
        "failed_score_count": run["failed_score_count"],
        "score_coverage": run["score_coverage"],
        "metric_names": run["metric_names"],
        "git_commit": _git_sha(),
        **evaluator.safe_dict(),  # never includes the API key
    }
    # allow_nan=False guarantees no non-standard NaN/inf can leak into JSON; by
    # this point scores are already normalised, so this is a fail-loud backstop.
    (out / "run_config.json").write_text(
        json.dumps(run_config, indent=2, allow_nan=False), encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps({"metrics": run["metrics"], "per_case": run["per_case"],
                    "run_config": run_config}, indent=2, allow_nan=False),
        encoding="utf-8")

    fieldnames = ["case_id", "category", *run["metric_names"]]
    with open(out / "results.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in run["per_case"]:
            writer.writerow(row)

    (out / "summary.md").write_text(_summary_md(run, run_config), encoding="utf-8")


def _summary_md(run: dict, run_config: dict) -> str:
    m = run["metrics"]
    lines = [
        "# RAGAS — generation quality\n",
        f"Run {run_config['timestamp']} · RAGAS {run_config['ragas_version']} · "
        f"evaluator `{run_config['evaluator_model']}` · {run['case_count']} case(s).",
        "Measured values (baseline — not pass/fail). Optional secondary layer; the "
        "deterministic retrieval evaluations remain the primary gate.\n",
        "## Execution status\n",
        f"Status: **{run['status']}**",
        f"Valid scores: {run['valid_score_count']} / {run['expected_score_count']}",
        f"Score coverage: {round(run['score_coverage'] * 100, 1)}%",
        ("\n_Some evaluator jobs did not return valid numeric scores. Metrics below "
         "are aggregated only from valid scores. This is technical evaluation "
         "coverage, not model quality._" if run["status"] == ra.STATUS_PARTIAL else ""),
        "",
        "## Overall\n",
        f"- Faithfulness: **{_fmt(m.get(ra.METRIC_FAITHFULNESS))}**",
        f"- Response Relevancy: **{_fmt(m.get(ra.METRIC_RESPONSE_RELEVANCY))}**",
        f"- Context Precision: **{_fmt(m.get(ra.METRIC_CONTEXT_PRECISION))}**",
        f"- Context Recall: **{_fmt(m.get(ra.METRIC_CONTEXT_RECALL))}** "
        f"({run['referenced_case_count']} referenced case(s))"
        if run["context_recall_run"] else
        "- Context Recall: not run (no referenced cases in this selection)",
        "",
        "## By category\n",
        "| Category | n | Faithfulness | Response Relevancy | Context Precision |",
        "|---|---|---|---|---|",
    ]
    by_cat: dict[str, list] = {}
    for row in run["per_case"]:
        by_cat.setdefault(row.get("category", ""), []).append(row)
    for cat in sorted(by_cat):
        rows = by_cat[cat]
        lines.append(
            f"| {cat or '—'} | {len(rows)} | "
            f"{_avg(rows, ra.METRIC_FAITHFULNESS)} | "
            f"{_avg(rows, ra.METRIC_RESPONSE_RELEVANCY)} | "
            f"{_avg(rows, ra.METRIC_CONTEXT_PRECISION)} |")

    lowest = sorted(
        (r for r in run["per_case"] if ra.is_valid_score(r.get(ra.METRIC_FAITHFULNESS))),
        key=lambda r: r[ra.METRIC_FAITHFULNESS])[:5]
    if lowest:
        lines += ["", "## Lowest-faithfulness cases (review, not automatic failures)\n"]
        for r in lowest:
            lines.append(f"- `{r['case_id']}` — faithfulness {r[ra.METRIC_FAITHFULNESS]}")
    return "\n".join(lines) + "\n"


def _fmt(value) -> str:
    # Defensively map None / NaN / inf → n/a; never render a non-finite value.
    return f"{value}" if ra.is_valid_score(value) else "n/a"


def _avg(rows, name) -> str:
    vals = [float(r[name]) for r in rows if ra.is_valid_score(r.get(name))]
    return f"{round(sum(vals) / len(vals), 3)}" if vals else "n/a"


if __name__ == "__main__":
    sys.exit(main())
