# RAGAS — generation-quality evaluation (design note)

RAGAS is an **optional, secondary** evaluation layer for Career Intelligence. It
does **not** replace the existing deterministic evaluation, and it is never part
of the user-response path or of normal CI.

## What the current evaluations measure (unchanged, primary)

| Suite | Measures |
|---|---|
| 11R (`eval_rag.py`) | Retrieval quality: Hit@K, MRR, Recall@K; query-translation experiment |
| 11R-A (`eval_expanded.py`) | Structured architecture: routing, structured-role/compensation, provenance |
| KB-2 (`eval_knowledge_expansion.py`) | Router accuracy, geographic precedence, coverage, record counts |
| Product coverage (`eval_product_coverage.py`) | Routing, geo precedence, evidence Hit@5, citation validity, salary context, tool selection, insufficient-evidence |
| quality_v2 (`eval_quality_v2.py`) | Held-out retrieval + tool selection + OOD separation |
| faithfulness_v2 (`eval_faithfulness_v2.py`) | Deterministic provenance/citation-precision/salary/insufficient checks |

These answer: **did the system retrieve the right evidence, route correctly, cite
validly, and refuse when evidence is thin?** They are deterministic, offline, and
remain the CI quality gate.

## What RAGAS adds (new, secondary)

RAGAS answers a *different* question — about the **generation**, not retrieval:

> Given the question, the retrieved context and the generated answer, how well did
> the generation use the evidence?

Metrics (RAGAS ≥0.2 API):

| Metric (this project) | RAGAS class | Plain-language question |
|---|---|---|
| Faithfulness | `Faithfulness` | Are the answer's claims supported by the retrieved context? |
| Response Relevancy | `ResponseRelevancy` (formerly *answer relevancy*) | Does the answer actually address the question? |
| Context Precision | `LLMContextPrecisionWithoutReference` | Was the retrieved context useful rather than noisy? |
| Context Recall | `LLMContextRecall` | Did retrieval capture enough of what a reference answer needs? (**reference required** — only run where a credible reference exists) |

RAGAS metrics use an **LLM evaluator**, so they carry cost and run-to-run
variability — hence optional and out of CI.

## Boundaries (non-negotiable)

- **Optional dependency** (`pip install -e ".[evaluation]"`); the base app and
  all existing tests run without RAGAS installed.
- **No paid/live calls in pytest.** Adapter tests mock RAGAS entirely.
- **Missing evaluator credentials → SKIPPED / NOT RUN**, never failure.
- **Public data only.** RAGAS runs against `evaluations/ragas/cases.json` — never
  real candidate backgrounds, job descriptions, interview transcripts, or private
  company files.
- **Never overwrites** 11R / 11R-A / KB-2 / product coverage / quality_v2 /
  faithfulness_v2. Every run writes to `evaluations/ragas/runs/<timestamp>/`.
- RAGAS is isolated from `CareerIntelligenceService`; the chat path works
  identically whether or not RAGAS is installed.

## Data contract

The adapter consumes a plain `RagasEvalCase` (no LangChain/Chroma/SQLite/Streamlit
objects): `question`, `answer`, `retrieved_contexts` (list of strings from the
answer's evidence/citations), optional `reference`/`reference_contexts`,
`source_ids`, and `metadata`. Application results are converted into this plain
shape before RAGAS sees them.

## Evaluator model

Configured independently of production chat via `RAGAS_EVAL_API_KEY`,
`RAGAS_EVAL_BASE_URL`, `RAGAS_EVAL_MODEL` (and optional `RAGAS_EVAL_EMBEDDING_MODEL`).
Missing → the CLI reports *"RAGAS evaluation not run — evaluator credentials not
configured."* and exits 0 (unless `--require-live`). The production chat key is
**not** reused unless the user explicitly opts in.

> **Common misconfiguration:** an OpenRouter key (`sk-or-…`) sent to the default
> OpenAI endpoint fails to authenticate, so every metric comes back NaN. Set
> `RAGAS_EVAL_BASE_URL=https://openrouter.ai/api/v1` (and OpenRouter-style model
> names). The CLI never prints the key; on failure it reports which of
> `RAGAS_EVAL_API_KEY` / `RAGAS_EVAL_BASE_URL` / `RAGAS_EVAL_MODEL` /
> `RAGAS_EVAL_EMBEDDING_MODEL` to check, plus a safe base-URL/model diagnostic.

## Execution status (technical validity, not model quality)

A valid metric score is a **finite real number**; `NaN`, `+inf`, `-inf` and
`None` are never stored and never aggregated. Each run gets a deterministic
status from how many *expected* scores came back valid (Context Recall is
expected only on referenced cases):

| Status | Rule | Persisted? |
|---|---|---|
| **COMPLETE** | every expected score is valid | yes |
| **PARTIAL** | some — but not all — scores are valid | yes (marked PARTIAL, with coverage) |
| **FAILED** | zero valid scores (e.g. evaluator auth failure) | **no** — the CLI exits non-zero (2) and writes no artifacts |

A FAILED run therefore can never look "completed": no `runs/<timestamp>/`
directory and no `results.*` are created. PARTIAL runs are written but clearly
flagged (`valid_score_count / expected_score_count`, `score_coverage`) so a
partial evaluator outage is not mistaken for a low model score. Artifacts are
written with `json.dumps(allow_nan=False)`, so a non-finite value can never leak
into `results.json` / `run_config.json`. The Evaluation page skips invalid/legacy
all-NaN runs and uses the newest *usable* run as the baseline (warning that an
invalid run was ignored); it never deletes historical folders.
