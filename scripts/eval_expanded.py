"""Runner hook for the expanded-architecture evaluation (Phase 11R-A).

Evaluates the new lanes (router, structured role, compensation), compares core
retrieval to the preserved 11R baseline, and writes:
  evaluations/expanded_architecture_results.csv
  evaluations/expanded_architecture_evaluation.md

It NEVER modifies the 11R artifacts (retrieval_results.csv, rag_evaluation.md,
tool_selection_results.csv) — those remain the baseline. The extended benchmark
run is intended for the next phase; this script is provided as the hook.

Usage:  python scripts/eval_expanded.py
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot import constants  # noqa: E402
from src.copilot.config import load_config  # noqa: E402
from src.copilot.embeddings import build_embedder  # noqa: E402
from src.copilot.evaluation.expanded_eval import (  # noqa: E402
    compare_to_baseline,
    evaluate_compensation,
    evaluate_router,
    evaluate_structured_role,
    load_baseline_retrieval,
    load_compensation_cases,
    load_role_cases,
    load_router_cases,
)
from src.copilot.evaluation.rag_eval import evaluate_retrieval, load_dataset  # noqa: E402
from src.copilot.ingestion import indexer  # noqa: E402
from src.copilot.knowledge import manifest as km  # noqa: E402
from src.copilot.knowledge import normalisers as norm  # noqa: E402
from src.copilot.knowledge.compensation import CompensationRecord, CompensationRepository  # noqa: E402
from src.copilot.knowledge.roles import RoleRepository  # noqa: E402
from src.copilot.retrieval import build_retriever  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402

OUT_DIR = "evaluations"
SAMPLES = "evaluations/knowledge_samples"
BASELINE_CSV = "evaluations/retrieval_results.csv"


def _role_repo() -> RoleRepository:
    repo = RoleRepository(":memory:")
    for row in json.load(open(f"{SAMPLES}/roles_onet.json")):
        repo.add_occupation(norm.normalise_onet(row))
    for row in json.load(open(f"{SAMPLES}/roles_esco.json")):
        repo.add_occupation(norm.normalise_esco(row))
    for occ in norm.normalise_isco(json.load(open(f"{SAMPLES}/isco.json"))):
        repo.add_occupation(occ)
    return repo


def _comp_repo() -> CompensationRepository:
    repo = CompensationRepository(":memory:")
    with open(f"{SAMPLES}/compensation.csv", newline="") as h:
        for row in csv.DictReader(h):
            row = {k: (v or None) for k, v in row.items()}
            row["year"] = int(row["year"]) if row["year"] else None
            for f in ("value", "lower_bound", "upper_bound"):
                row[f] = float(row[f]) if row[f] else None
            repo.add(CompensationRecord(**row))
    return repo


def main() -> int:
    entries = km.load_manifest(constants.SOURCE_MANIFEST_PATH)
    config = load_config().model_copy(update={"embedding_provider": "local"})

    router = evaluate_router(load_router_cases(f"{OUT_DIR}/router_cases.json"))
    role = evaluate_structured_role(_role_repo(), load_role_cases(f"{OUT_DIR}/structured_role_cases.json"), entries)
    comp = evaluate_compensation(_comp_repo(), load_compensation_cases(f"{OUT_DIR}/compensation_cases.json"), entries)

    # Re-run 11R retrieval to compare against the preserved baseline.
    store = build_vector_store(config, embedder=build_embedder(config), in_memory=True)
    chunks, _ = indexer.ingest_directory("evaluations/corpus")
    store.add_chunks(chunks)
    cases, top_k = load_dataset("evaluations/rag_dataset.json")
    current = {m: build_retriever(config, mode=m, store=store) for m in constants.RETRIEVAL_MODES}
    retrieval = {mode: met.as_dict() for mode, met in evaluate_retrieval(current, cases, top_k).items()}
    current_simple = {m: {"hit_rate@k": v["hit_rate_at_k"], "mrr": v["mrr"], "recall@k": v["recall_at_k"]}
                      for m, v in retrieval.items()}
    diffs = {}
    if Path(BASELINE_CSV).is_file():
        diffs = compare_to_baseline(load_baseline_retrieval(BASELINE_CSV), current_simple)

    _write_csv(router, role, comp, current_simple, diffs)
    _write_md(router, role, comp, current_simple, diffs)
    print(f"router acc={router['accuracy']} · role hit={role['hit_rate']} "
          f"prov={role['provenance_completeness']} · comp acc={comp['accuracy']}")
    print(f"Wrote {OUT_DIR}/expanded_architecture_results.csv and .md "
          "(11R baseline artifacts untouched).")
    return 0


def _write_csv(router, role, comp, current, diffs) -> None:
    with open(f"{OUT_DIR}/expanded_architecture_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "key", "metric", "value"])
        w.writerow(["router", "overall", "accuracy", router["accuracy"]])
        for lane, acc in router["by_lane"].items():
            w.writerow(["router", lane, "accuracy", acc])
        for k, v in (("hit_rate", role["hit_rate"]), ("provenance_completeness", role["provenance_completeness"]), ("avg_latency_ms", role["avg_latency_ms"])):
            w.writerow(["structured_role", "overall", k, v])
        for k, v in (("accuracy", comp["accuracy"]), ("provenance_completeness", comp["provenance_completeness"])):
            w.writerow(["compensation", "overall", k, v])
        for mode, m in current.items():
            for k, v in m.items():
                w.writerow(["retrieval_current", mode, k, v])
        for mode, m in diffs.items():
            for k, v in m.items():
                w.writerow(["retrieval_diff_vs_baseline", mode, k, v])


def _write_md(router, role, comp, current, diffs) -> None:
    lines = [
        "# Expanded Career Intelligence — Evaluation (11R-A)",
        "",
        "Phase 11R established the initial RAG benchmark (preserved in "
        "`retrieval_results.csv` / `rag_evaluation.md`). This 11R-A report measures "
        "the expanded multi-lane architecture and compares core retrieval to that "
        "baseline. 11R artifacts are unchanged.",
        "",
        "## Routing accuracy",
        f"- Overall: **{router['accuracy']}** ({router['correct']}/{router['total']})",
        "- By lane: " + ", ".join(f"{k}={v}" for k, v in router["by_lane"].items()),
        "",
        "## Structured role retrieval",
        f"- Hit rate: **{role['hit_rate']}** · provenance completeness: "
        f"**{role['provenance_completeness']}** · latency: {role['avg_latency_ms']} ms",
        "",
        "## Compensation retrieval",
        f"- Accuracy (country+year+currency+statistic+source): **{comp['accuracy']}** · "
        f"provenance completeness: **{comp['provenance_completeness']}**",
        "",
        "## Core retrieval vs 11R baseline",
        "",
        "| mode | hit@k | mrr | recall@k | Δ hit | Δ mrr | Δ recall |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode, m in current.items():
        d = diffs.get(mode, {})
        lines.append(
            f"| {mode} | {m['hit_rate@k']} | {m['mrr']} | {m['recall@k']} | "
            f"{d.get('hit_rate@k', '—')} | {d.get('mrr', '—')} | {d.get('recall@k', '—')} |"
        )
    lines += [
        "",
        "## Findings & limitations",
        "- The expanded architecture ADDS lanes; it does not change narrative vector "
        "retrieval, so core hit@k/MRR/recall are expected to match the baseline "
        "(Δ ≈ 0). Improvement is in **coverage**: structured role and compensation "
        "questions that vector RAG could not answer precisely are now served by "
        "dedicated lanes with provenance.",
        "- Numbers reflect the committed synthetic samples; real datasets refine them.",
        "- Regressions, if any, are shown in the Δ columns and are not hidden.",
    ]
    with open(f"{OUT_DIR}/expanded_architecture_evaluation.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
