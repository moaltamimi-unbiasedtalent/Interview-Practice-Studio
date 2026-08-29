"""Configurable retrieval-quality evaluation (OPT-1D).

Runs a config matrix over the local narrative corpus and records full provenance
(embedding provider/model, chunk strategy, retrieval strategy, hybrid weights,
reranker, top_k, corpus fingerprint, timestamp) plus Hit@K / MRR / Recall@K /
latency. Never overwrites 11R / 11R-A — writes only under
``evaluations/retrieval_quality_v2/``.

Offline-safe: the local-hash (lexical) configs always run. Semantic configs run
ONLY if a dedicated embedding credential is configured; otherwise they are
reported as "SEMANTIC EVALUATION NOT RUN — CREDENTIAL NOT CONFIGURED" with the
exact command. Local-hash results are never labelled semantic.

Usage:  python scripts/eval_retrieval_quality_v2.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.copilot.config import load_config  # noqa: E402
from src.copilot.embeddings import LocalHashEmbedder, embedding_status  # noqa: E402
from src.copilot.evaluation.rag_eval import evaluate_retrieval, load_dataset  # noqa: E402
from src.copilot.ingestion import indexer  # noqa: E402
from src.copilot.retrieval import build_retriever  # noqa: E402
from src.copilot.vectorstore import build_vector_store  # noqa: E402

CORPUS = "evaluations/corpus"
DATASET = "evaluations/rag_dataset.json"
OUT = Path("evaluations/retrieval_quality_v2")


def _corpus_fingerprint() -> str:
    h = hashlib.sha256()
    for p in sorted(Path(CORPUS).rglob("*")):
        if p.is_file():
            h.update(p.name.encode()); h.update(str(p.stat().st_size).encode())
    return h.hexdigest()[:16]


def _run_local(config, *, chunking: str, modes: list[str]) -> dict:
    embedder = LocalHashEmbedder()
    store = build_vector_store(config, embedder=embedder, in_memory=True)
    chunks, _ = indexer.ingest_directory(CORPUS, chunking_strategy=chunking)
    store.add_chunks(chunks)
    cases, top_k = load_dataset(DATASET)
    retrievers = {m: build_retriever(config, mode=m, store=store) for m in modes}
    t0 = time.perf_counter()
    metrics = evaluate_retrieval(retrievers, cases, top_k)
    latency = round((time.perf_counter() - t0) * 1000, 2)
    out = {}
    for mode, m in metrics.items():
        md = m.__dict__ if hasattr(m, "__dict__") else dict(m)
        out[mode] = {**md, "chunks": len(chunks)}
    return {"metrics": out, "top_k": top_k, "latency_ms": latency, "chunks": len(chunks)}


def main() -> int:
    config = load_config()
    status = embedding_status(config)
    semantic_available = status["quality_mode"] == "SEMANTIC"
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    fp = _corpus_fingerprint()

    report = {
        "generated": stamp, "corpus": CORPUS, "corpus_fingerprint": fp,
        "dataset": DATASET, "semantic_available": semantic_available,
        "embedding_status": status, "runs": [],
    }

    # Configs that CAN run offline (local hash / lexical).
    offline_configs = [
        {"name": "1_localhash_baseline", "embedding": "local", "chunking": "baseline",
         "modes": ["vector", "keyword", "hybrid"]},
        {"name": "3b_localhash_section", "embedding": "local", "chunking": "section",
         "modes": ["hybrid"]},
    ]
    for cfg in offline_configs:
        result = _run_local(config, chunking=cfg["chunking"], modes=cfg["modes"])
        report["runs"].append({
            **cfg, "embedding_model": "local-hash-v1",
            "hybrid_weights": [config.hybrid_vector_weight, config.hybrid_keyword_weight],
            "reranker": "none", **result})

    # Semantic configs — only if a dedicated embedding credential exists.
    semantic_configs = [
        "2_semantic_baseline", "3_semantic_section", "4_semantic_hybrid",
        "5_semantic_hybrid_reranker",
    ]
    if semantic_available:
        report["semantic_note"] = ("Semantic credential detected; run per-config "
                                   "manually to avoid unexpected paid calls.")
    else:
        report["semantic_note"] = (
            "SEMANTIC EVALUATION NOT RUN — CREDENTIAL NOT CONFIGURED. "
            "Set COPILOT_EMBEDDING_API_KEY (and COPILOT_EMBEDDING_PROVIDER=openai) "
            "then re-run: python scripts/eval_retrieval_quality_v2.py")
        for name in semantic_configs:
            report["runs"].append({"name": name, "status": "NOT_RUN",
                                   "reason": "no dedicated embedding credential"})

    (OUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    lines = ["# Retrieval Quality v2\n",
             f"Generated {stamp} · corpus `{CORPUS}` (fp {fp}) · dataset `{DATASET}`.",
             f"Embedding: **{status['quality_mode']}** ({status['provider']}/{status['model']}).\n",
             f"> {report['semantic_note']}\n",
             "Does not modify 11R / 11R-A artifacts.\n",
             "## Offline (lexical) runs\n",
             "| Config | Mode | Hit@K | MRR | Recall@K | chunks |",
             "|---|---|---|---|---|---|"]
    for run in report["runs"]:
        if run.get("status") == "NOT_RUN":
            continue
        for mode, m in run["metrics"].items():
            lines.append(f"| {run['name']} | {mode} | {m.get('hit_rate_at_k','?')} | "
                         f"{m.get('mrr','?')} | {m.get('recall_at_k','?')} | "
                         f"{run['chunks']} |")
    not_run = [r["name"] for r in report["runs"] if r.get("status") == "NOT_RUN"]
    if not_run:
        lines.append("\n## Semantic runs — NOT RUN (no credential)\n")
        for n in not_run:
            lines.append(f"- {n}")
    (OUT / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT}/results.json + summary.md")
    print(f"Semantic available: {semantic_available} — {report['semantic_note'][:60]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
