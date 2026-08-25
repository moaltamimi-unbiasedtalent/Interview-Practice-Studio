"""Run the Career Intelligence RAG evaluation and write reports.

Deterministic and offline by default: it forces the local embedder and the
heuristic query translator so results are reproducible and free. Run with an LLM
translator / OpenAI embeddings to refine the semantic numbers.

Outputs:
  evaluations/retrieval_results.csv
  evaluations/tool_selection_results.csv
  evaluations/rag_evaluation.md

Usage:
  python scripts/eval_rag.py
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
from src.copilot.evaluation.rag_eval import (  # noqa: E402
    ToolCase,
    evaluate_citations,
    evaluate_retrieval,
    evaluate_tool_selection,
    evaluate_translation,
    load_dataset,
)
from src.copilot.ingestion import indexer  # noqa: E402
from src.copilot.rag.translation import QueryTranslator  # noqa: E402
from src.copilot.retrieval import build_retriever  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402

CORPUS = "evaluations/corpus"
DATASET = "evaluations/rag_dataset.json"
TOOL_CASES = "evaluations/tool_selection_cases.json"
OUT_DIR = "evaluations"


def _build_store(config):
    embedder = build_embedder(config)
    store = build_vector_store(config, embedder=embedder, in_memory=True)
    chunks, report = indexer.ingest_directory(CORPUS)
    store.add_chunks(chunks)
    return store, embedder, report


def main() -> int:
    # Force deterministic, offline settings for a reproducible benchmark.
    config = load_config().model_copy(update={"embedding_provider": "local"})
    store, embedder, ingest_report = _build_store(config)
    if store.count() == 0:
        print(f"No corpus indexed from {CORPUS}.")
        return 1

    cases, top_k = load_dataset(DATASET)
    retrievers = {m: build_retriever(config, mode=m, store=store) for m in constants.RETRIEVAL_MODES}

    retrieval = evaluate_retrieval(retrievers, cases, top_k)
    translation = evaluate_translation(
        retrievers["hybrid"], QueryTranslator(enabled=False), cases, top_k
    )
    citations = evaluate_citations(retrievers["hybrid"], cases, top_k)

    with open(TOOL_CASES, encoding="utf-8") as handle:
        tool_cases = [ToolCase(**c) for c in json.load(handle)["cases"]]
    tools = evaluate_tool_selection(tool_cases)

    _write_retrieval_csv(retrieval, translation)
    _write_tool_csv(tools)
    _write_markdown(
        config, embedder, ingest_report, top_k, len(cases),
        retrieval, translation, citations, tools,
    )

    print(f"Indexed {store.count()} chunks from {ingest_report.documents} docs "
          f"(embedder: {embedder.provider}/{embedder.model}).")
    for mode, m in retrieval.items():
        print(f"  {mode:<8} hit@{top_k}={m.hit_rate_at_k} mrr={m.mrr} "
              f"recall@{top_k}={m.recall_at_k} term={m.term_recall_at_k} "
              f"lat={m.avg_latency_ms}ms")
    print(f"  translation: original mrr={translation['original'].mrr} "
          f"→ translated mrr={translation['translated'].mrr}")
    print(f"  tool selection accuracy: {tools['accuracy']}")
    print(f"  citation valid-id rate: {citations['valid_id_mapping_rate']}")
    print(f"\nWrote reports under {OUT_DIR}/.")
    return 0


def _write_retrieval_csv(retrieval, translation) -> None:
    with open(f"{OUT_DIR}/retrieval_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["group", "mode", "cases", "hit_rate@k", "mrr", "recall@k", "term_recall@k", "avg_latency_ms"])
        for m in retrieval.values():
            w.writerow(["retrieval", m.mode, m.cases, m.hit_rate_at_k, m.mrr, m.recall_at_k, m.term_recall_at_k, m.avg_latency_ms])
        for m in translation.values():
            w.writerow(["translation", m.mode, m.cases, m.hit_rate_at_k, m.mrr, m.recall_at_k, m.term_recall_at_k, m.avg_latency_ms])


def _write_tool_csv(tools) -> None:
    with open(f"{OUT_DIR}/tool_selection_results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["id", "expected_tools", "selected_tools", "correct"])
        for d in tools["details"]:
            w.writerow([d["id"], "|".join(d["expected"]), "|".join(d["selected"]), d["correct"]])
        w.writerow([])
        w.writerow(["accuracy", tools["accuracy"], "correct", f"{tools['correct']}/{tools['total']}"])


def _md_table(rows, headers) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(out)


def _write_markdown(config, embedder, ingest_report, top_k, n_cases, retrieval, translation, citations, tools) -> None:
    best = max(retrieval.values(), key=lambda m: (m.mrr, m.hit_rate_at_k))
    lines = [
        "# Career Intelligence — RAG Evaluation",
        "",
        f"Dataset: **{n_cases} cases**, top_k=**{top_k}**, over a committed corpus of "
        f"**{ingest_report.documents} documents** (`evaluations/corpus/`).",
        f"Embedder: **{embedder.provider}/{embedder.model}**. Translator: **heuristic "
        "(offline)**. This run is deterministic and free; see caveats below.",
        "",
        "## 1. Retrieval strategies (vector / keyword / hybrid)",
        "",
        _md_table(
            [[m.mode, m.hit_rate_at_k, m.mrr, m.recall_at_k, m.term_recall_at_k, m.avg_latency_ms]
             for m in retrieval.values()],
            [f"mode", f"Hit@{top_k}", "MRR", f"Recall@{top_k}", f"TermRecall@{top_k}", "Latency (ms)"],
        ),
        "",
        f"Best by MRR then Hit@{top_k}: **{best.mode}**.",
        "",
        "## 2. Query-translation experiment",
        "",
        _md_table(
            [[m.mode, m.hit_rate_at_k, m.mrr, m.recall_at_k, m.avg_latency_ms]
             for m in translation.values()],
            [f"query", f"Hit@{top_k}", "MRR", f"Recall@{top_k}", "Latency (ms)"],
        ),
        "",
        "> Translation ran with the **offline heuristic** translator, which returns "
        "the original query with no alternates — so 'translated' equals 'original' "
        "here. This is reported honestly: no translation effect is measurable "
        "offline. Re-run with an LLM translator to measure the semantic effect. We "
        "do **not** assume translation is better.",
        "",
        "## 3. Tool selection",
        "",
        f"Accuracy: **{tools['accuracy']}** ({tools['correct']}/{tools['total']} cases).",
        "",
        _md_table(
            [[d["id"], "|".join(d["expected"]) or "—", "|".join(d["selected"]) or "—", d["correct"]]
             for d in tools["details"]],
            ["id", "expected", "selected", "correct"],
        ),
        "",
        "## 4. Citation correctness",
        "",
        f"- Cases considered: {citations['cases_considered']}",
        f"- Citation ids map to retrieved chunks: **{citations['valid_id_mapping_rate']}**",
        f"- Cited source exists (title/source present): **{citations['source_exists_rate']}**",
        "",
        "Citations are constructed from the retrieved passages, so by design every "
        "marker maps to a real retrieved chunk; this check validates that invariant.",
        "",
        "## 5. Honest caveats",
        "",
        "- The **local hashing embedder** is lexical, not semantic, so vector numbers "
        "understate what OpenAI embeddings would achieve; hybrid/keyword benefit on "
        "exact-term probes. Re-run with `COPILOT_EMBEDDING_API_KEY` for semantic vector.",
        "- The corpus is a small **synthetic** set of general career facts for a "
        "reproducible benchmark; absolute numbers reflect that corpus.",
        "- We do **not** rewrite results to favour hybrid. If hybrid does not win on a "
        "metric, the table shows it; likely reasons: a lexical embedder narrows the "
        "gap between vector and keyword, and single-source questions cap Recall@k.",
    ]
    with open(f"{OUT_DIR}/rag_evaluation.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    sys.exit(main())
