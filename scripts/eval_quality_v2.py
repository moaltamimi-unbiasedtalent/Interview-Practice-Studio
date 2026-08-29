"""Held-out quality evaluation (OPT-7): retrieval, tool selection, OOD, faithfulness.

Runs a HELD-OUT set (evaluations/quality_v2/held_out_relevance.json) authored
after the system was built and never used to tune it. All checks are deterministic
and offline (local lexical embedder); nothing here makes a paid/live call. An
optional LLM-judge is described but reported as NOT RUN unless a credential is
configured. Writes only under evaluations/quality_v2/ — never touches 11R / 11R-A
or product-coverage artifacts.

Usage:  python scripts/eval_quality_v2.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.config import load_config  # noqa: E402
from src.copilot.embeddings import LocalHashEmbedder, embedding_status  # noqa: E402
from src.copilot.evaluation.rag_eval import (  # noqa: E402
    RagCase,
    _ranked_sources,
    _term_hit,
    evaluate_retrieval,
)
from src.copilot.ingestion import indexer  # noqa: E402
from src.copilot.rag.routing import route_for_intent  # noqa: E402
from src.copilot.retrieval import build_retriever  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402

CORPUS = "evaluations/corpus"
DATASET = Path("evaluations/quality_v2/held_out_relevance.json")
OUT = Path("evaluations/quality_v2")


def _cases(rows: list[dict]) -> list[RagCase]:
    return [RagCase(id=r["id"], question=r["question"], category="held_out",
                    expected_sources=r.get("expected_sources", []),
                    expected_terms=r.get("expected_terms", [])) for r in rows]


def main() -> int:
    config = load_config()
    data = json.loads(DATASET.read_text(encoding="utf-8"))
    top_k = int(data.get("top_k", 5))
    store = build_vector_store(config, embedder=LocalHashEmbedder(), in_memory=True)
    chunks, _ = indexer.ingest_directory(CORPUS)
    store.add_chunks(chunks)
    retriever = build_retriever(config, mode="hybrid", store=store)

    # 1) Held-out retrieval quality.
    rel_cases = _cases(data["relevance"])
    retrieval = {m: v.as_dict() for m, v in
                 evaluate_retrieval({"hybrid": retriever}, rel_cases, top_k).items()}

    # 2) Tool-selection accuracy (deterministic route table).
    tool_rows = data.get("tool_selection", [])
    tool_correct = 0
    tool_detail = []
    for row in tool_rows:
        got = sorted(route_for_intent(row["intent"]).tools)
        exp = sorted(row["expected_tools"])
        ok = got == exp
        tool_correct += int(ok)
        tool_detail.append({"id": row["id"], "intent": row["intent"],
                            "expected": exp, "got": got, "ok": ok})
    tool_acc = round(tool_correct / (len(tool_rows) or 1), 3)

    # 3) Out-of-domain separation via lexical query-content overlap.
    # With the offline lexical embedder, similarity SCORES are near-uniform, so a
    # score threshold is not discriminative. Instead we measure how much of a
    # query's own content words appear in the top retrieved chunk: in-domain
    # queries share vocabulary with the corpus, OOD queries (pizza / weather /
    # football) do not, so a downstream "insufficient evidence" guard can catch
    # them. A leak = an OOD query whose overlap reaches the weakest in-domain one.
    _STOP = {"what", "which", "how", "the", "a", "an", "to", "for", "of", "in",
             "is", "are", "do", "does", "should", "i", "my", "at", "with", "and",
             "on", "will", "be", "someone", "actually", "good", "into", "modern"}

    def overlap(q: str) -> float:
        res = retriever.retrieve(q, top_k=top_k)
        if not res:
            return 0.0
        words = {w for w in "".join(c for c in q.lower() if c.isalnum() or c == " ").split()
                 if w not in _STOP and len(w) > 2}
        if not words:
            return 0.0
        hay = " ".join((r.chunk.text or "").lower() for r in res[:top_k])
        return round(sum(1 for w in words if w in hay) / len(words), 3)

    in_ov = [overlap(c.question) for c in rel_cases]
    ood_rows = data.get("out_of_domain", [])
    ood_ov = [overlap(r["question"]) for r in ood_rows]
    in_min = min(in_ov) if in_ov else 0.0
    ood_leaks = sum(1 for s in ood_ov if s >= in_min and s > 0)
    ood = {
        "metric": "query-content lexical overlap with top-k chunks",
        "in_domain_overlap_mean": round(sum(in_ov) / (len(in_ov) or 1), 3),
        "ood_overlap_mean": round(sum(ood_ov) / (len(ood_ov) or 1), 3),
        "in_domain_overlap_min": round(in_min, 3),
        "ood_leaks_at_in_domain_min": ood_leaks,
        "ood_cases": len(ood_rows),
    }

    # 4) Faithfulness: reference the committed deterministic faithfulness_v2
    # artifact (produced by scripts/eval_faithfulness_v2.py) — not recomputed here.
    faith_path = Path("evaluations/faithfulness_v2/summary.md")
    faithfulness = {"status": "SEE evaluations/faithfulness_v2/",
                    "present": faith_path.is_file()}

    # 5) Optional LLM-judge — gated behind a credential; NEVER run in CI.
    status = embedding_status(config)
    llm_judge = {
        "status": "NOT RUN",
        "reason": ("LLM-judge is optional and disabled by default; it requires a "
                   "chat credential and is never run in CI."),
        "how_to_run": "Provide COPILOT_API_KEY and re-run with a future --llm-judge flag.",
    }

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = {
        "generated": stamp, "held_out_dataset": str(DATASET),
        "corpus": CORPUS, "embedding_mode": status["quality_mode"], "top_k": top_k,
        "retrieval": retrieval, "tool_selection_accuracy": tool_acc,
        "tool_selection_detail": tool_detail, "out_of_domain": ood,
        "faithfulness": faithfulness, "llm_judge": llm_judge,
        "note": "Held-out, deterministic, offline. Does not modify 11R/11R-A.",
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    hy = retrieval["hybrid"]
    lines = [
        "# Quality v2 — held-out evaluation\n",
        f"Generated {stamp} · embedding **{status['quality_mode']}** · top_k={top_k}.",
        "Held-out set authored after build; deterministic + offline; 11R/11R-A untouched.\n",
        "## Held-out retrieval (hybrid, lexical)\n",
        f"- Hit@{top_k}: **{hy['hit_rate_at_k']}** · MRR: **{hy['mrr']}** · "
        f"Recall@{top_k}: **{hy['recall_at_k']}** · term-recall: {hy['term_recall_at_k']} "
        f"({hy['cases']} cases)\n",
        "## Tool selection\n",
        f"- Accuracy: **{tool_acc}** over {len(tool_rows)} known-intent cases.\n",
        "## Out-of-domain separation (lexical query-content overlap)\n",
        f"- In-domain overlap mean: {ood['in_domain_overlap_mean']} "
        f"(min {ood['in_domain_overlap_min']}); OOD overlap mean: {ood['ood_overlap_mean']}.",
        f"- OOD leaks at in-domain min: **{ood['ood_leaks_at_in_domain_min']}** / "
        f"{ood['ood_cases']}.\n",
        "## Faithfulness\n",
        f"- {'Present' if faithfulness['present'] else 'Not found'}: "
        "see `evaluations/faithfulness_v2/` (run `python scripts/eval_faithfulness_v2.py`).\n",
        "## LLM-judge\n",
        f"- {llm_judge['status']} — {llm_judge['reason']}\n",
    ]
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}/results.json + summary.md")
    print(f"Retrieval Hit@{top_k}={hy['hit_rate_at_k']} MRR={hy['mrr']} | "
          f"tool acc={tool_acc} | OOD leaks={ood['ood_leaks_at_in_domain_min']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
