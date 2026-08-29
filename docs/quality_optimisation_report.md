# Quality, Retrieval and UX Optimisation — Report (PHASE OPT)

Branch: `feature/career-intelligence-quality-optimisation` (from `main`).
This phase raised Career Intelligence retrieval quality, hybrid calibration,
citation faithfulness, performance, guided UX, naming/scoping, held-out
evaluation, and knowledge freshness — **without** fabricating metrics, making
paid/live calls in CI, or overwriting the historical 11R / 11R-A / KB-2 /
product-coverage benchmarks. The audit that scoped the work is
[`quality_optimisation_audit.md`](quality_optimisation_audit.md).

## What shipped, by section

| Section | Delivered | Key files |
|---|---|---|
| OPT-0 | Gap audit classifying every item ALREADY/PARTIAL/NOT/N-R | `docs/quality_optimisation_audit.md` |
| OPT-1 | Embedding status (SEMANTIC vs OFFLINE LEXICAL) + sidebar warning; `BaseReranker`/`NoOpReranker`/`LLMReranker`; section-aware chunking; offline retrieval-quality v2 harness | `src/copilot/embeddings.py`, `retrieval/reranker.py`, `ingestion/chunking.py`, `scripts/eval_retrieval_quality_v2.py` |
| OPT-2 | Hybrid weight validation; optional deterministic adaptive weighting + dominant-signal; inspector calibration panel | `config.py`, `retrieval/adaptive.py`, `service.py`, `career/ui.py` |
| OPT-3 | Invalid `[n]` markers stripped from answers; structured-facts panel; evidence/guidance UX; deterministic faithfulness v2 | `security/output_guard.py`, `career/ui.py`, `scripts/eval_faithfulness_v2.py` |
| OPT-4 | Session TTL cache (translation); quality/balanced/cheap modes | `copilot/cache.py`, `service.py` |
| OPT-5 | Dry-run plan (`plan()`); journey progress stepper; handoff provenance labels; synthetic demo knowledge pack | `service.py`, `ui/home.py`, `scripts/load_sample_knowledge.py` |
| OPT-6 | Distribution renamed `interview-os-coach`; reviewer-mode nav filter; canonical copilot/career split doc | `pyproject.toml`, `ui/navigation.py`, `app.py`, `docs/architecture.md` |
| OPT-7 | Held-out retrieval + tool + OOD + faithfulness evaluation; human review template | `evaluations/quality_v2/`, `scripts/eval_quality_v2.py` |
| OPT-8 | Deterministic source freshness (CURRENT/REFRESH DUE/UNKNOWN); health panel + answer-level freshness; offline check + dry-run refresh helpers | `knowledge/status.py`, `career/ui.py`, `scripts/check_source_freshness.py`, `scripts/refresh_public_sources.py` |

## Measured results (as run, offline)

- **Held-out retrieval** (`evaluations/quality_v2/`, hybrid, lexical embedder):
  Hit@5 **0.917**, MRR **0.704**, Recall@5 **0.917** over 12 held-out cases whose
  questions are disjoint from `rag_dataset.json`.
- **Tool selection**: **100%** over 6 known-intent cases (fixed route table).
- **Out-of-domain separation** (lexical query-content overlap): in-domain mean
  **0.669** (min 0.167) vs OOD **0.0** — **0 leaks**.
- **Faithfulness v2** (`evaluations/faithfulness_v2/`, deterministic): provenance
  100%, citation precision 100%, salary context 100%, insufficient-handling 88%.
- **Retrieval quality v2** (`evaluations/retrieval_quality_v2/`, lexical): matches
  the 11R baseline for the local-hash config; semantic configs report
  **SEMANTIC EVALUATION NOT RUN — CREDENTIAL NOT CONFIGURED** with the exact
  command (local-hash results are never labelled semantic).
- **Knowledge freshness**: of 26 available sources, 9 CURRENT, 0 REFRESH DUE,
  17 UNKNOWN (no reference year or no defined cadence — never asserted as stale).

## Semantic evaluation

No dedicated embedding credential is configured, so semantic retrieval was **not**
run (no paid/live calls). To evaluate semantic quality:

```bash
export COPILOT_EMBEDDING_API_KEY=...      # a dedicated embeddings key
export COPILOT_EMBEDDING_PROVIDER=openai
python scripts/eval_retrieval_quality_v2.py
```

The app still starts and answers with the offline lexical embedder; the sidebar
states the mode honestly.

## Final quality gate (as run)

| Check | Result |
|---|---|
| `compileall app.py src scripts tests` | OK |
| Import checks (app + key modules) | OK |
| Source manifest validation | OK (29 sources) |
| `pytest -q` | **1142 passed, 1 skipped** |
| Knowledge expansion eval | routing 100%, geo 100%, coverage 26/29, 15 211 records |
| Product coverage (7 gates) | routing 100%, geo 95%, hit@5 94%, citation 100%, salary 100%, tool 100%, insufficient 97% |
| Secret scan | No secrets found |

## Non-negotiables honoured

- Historical evaluations preserved — 11R / 11R-A / KB-2 / product-coverage
  artifacts untouched; all new work lives under `*_v2/` directories.
- No fabricated metrics; latency-only artifact churn was reverted, not committed.
- No paid/live calls in CI; a missing API key never blocks start-up.
- Security posture intact: prompt-injection scanning, RAG guard, output guard
  (now also stripping invalid citations), fixed tool registry, and the
  structured-data / PreparationContext trust boundaries are all unchanged.
- No raw candidate background, JD, transcript, retrieved private content, or API
  keys are logged; `embedding_status` and cache stats expose booleans/counts only.
- Existing interfaces were extended rather than rewritten.

## Reviewer notes

- Enable the Advanced diagnostic pages with `COPILOT_REVIEWER_MODE=true`.
- Regenerate held-out and freshness artifacts:
  `python scripts/eval_quality_v2.py`, `python scripts/check_source_freshness.py`.
- Try the app with no data via `python scripts/load_sample_knowledge.py`
  (clearly-synthetic, never production-ready).

Not merged to `main` — this branch is pushed for review.
