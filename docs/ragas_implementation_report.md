# RAGAS implementation report (PHASE RAGAS-1)

## Summary

Added RAGAS as an **optional, secondary** generation-quality evaluation layer for
Career Intelligence. The existing deterministic evaluation (11R, 11R-A, KB-2,
product coverage, quality_v2, faithfulness_v2) is unchanged and remains the
primary CI quality gate.

## Update — RAGAS-1B: fail-safe score validation (all-NaN guard)

A real live run exposed a failure mode: the evaluator failed to authenticate (an
OpenRouter key sent to the default OpenAI endpoint because `RAGAS_EVAL_BASE_URL`
was unset), RAGAS caught per-job exceptions, every metric became NaN, yet the CLI
still wrote a full run that *looked* completed. Fixed without redesign:

- **Valid score = finite real number.** `is_valid_score()` rejects `NaN`, `±inf`,
  `None` and bool. Per-case merge and aggregation store/average only valid scores;
  an aggregate with no valid values is `None`, never `NaN`.
- **Execution status** COMPLETE / PARTIAL / FAILED derived from valid vs expected
  score counts (Context Recall expected only on referenced cases). Run metadata
  adds `valid_score_count`, `expected_score_count`, `failed_score_count`,
  `valid_case_count`, `score_coverage`, `status`, and `has_usable_scores()`.
- **CLI hard stop:** a FAILED run (zero valid scores) prints `RAGAS RUN FAILED`,
  a safe config diagnostic (base-URL configured/default, model, embedding model —
  never the key), exits **2**, and writes **no** directory or artifacts. PARTIAL
  and COMPLETE runs are written, with status/coverage in `run_config.json`,
  `results.json` and `summary.md`.
- **JSON safety:** artifacts use `json.dumps(allow_nan=False)` so a non-finite
  value can never leak into standard JSON.
- **Evaluation page:** skips invalid/legacy all-NaN runs and shows the newest
  usable run (warning that an invalid run was ignored); PARTIAL runs show a
  coverage warning; nothing renders as `nan`.
- **Known failed local runs:** `evaluations/ragas/runs/20260902_073016/` and
  `.../20260902_074506/` contain authentication-failure NaN scores and must **not**
  be used as a baseline. `evaluations/ragas/runs/` is now git-ignored (generated,
  local-only); historical folders are never deleted automatically — remove local
  failed runs manually if desired.

Status is **technical execution coverage, not model quality**; no pass/fail
performance threshold is introduced.

## Update — RAGAS-2: run RAGAS safely from the Evaluation page

RAGAS can now be launched from the UI without the terminal, with every safeguard
intact:

- **Shared runner** `src/copilot/evaluation/ragas_runner.py` (`run_live_ragas`,
  `check_configuration`, `write_artifacts`) is the single evaluation
  implementation. `scripts/eval_ragas.py` and the Evaluation page are both thin
  interfaces over it — no duplicated logic; the CLI is not shelled out to.
- **Guarded controls** on *Review & diagnostics → Evaluation → RAGAS — Generation
  Quality*: three fixed scopes (2 / 10 / 35 public cases — no free-form counts),
  a required "makes live provider calls" checkbox, and a safe configuration status
  (package / evaluator credential / Career model / evaluator model / embedding /
  base-URL — **never the key**). The Run button stays disabled until configuration
  is complete and the box is ticked; a run in progress cannot be re-triggered.
- **Never on page open** — RAGAS executes only when the button is clicked.
- **Results by status** — success (COMPLETE), warning with coverage (PARTIAL),
  error with no baseline saved (FAILED). Metric legends and a COMPLETE/PARTIAL/
  FAILED explainer are shown; no pass/fail thresholds.
- **Security** — only `evaluations/ragas/cases.json` is evaluated; no chat,
  candidate background, JD, transcript, or company data. Session state holds only
  bounded, secret-free status.
- **OpenRouter** — `check_configuration` warns (safely, without the key) when an
  OpenRouter-style key is set with a default base URL, the exact misconfiguration
  that caused the earlier all-NaN failure.

## What was implemented

| Item | Location |
|---|---|
| Design note (current vs RAGAS metrics) | `docs/ragas_evaluation.md` |
| Optional dependency group | `pyproject.toml` → `[project.optional-dependencies].evaluation` |
| Plain evaluation contract + adapter | `src/copilot/evaluation/ragas_adapter.py` |
| Public held-out cases (35) + README | `evaluations/ragas/cases.json`, `evaluations/ragas/README.md` |
| CLI | `scripts/eval_ragas.py` |
| Evaluation-page section (read-only) | `src/career/ui.py` (`_render_ragas_section`) |
| Offline tests (mocked) | `tests/test_ragas_adapter.py` |
| Docs | README, `docs/rag.md`, `docs/architecture.md`, `docs/reviewer_guide.md`, `docs/quality_optimisation_report.md` |

## RAGAS version / API

- Pinned `ragas>=0.2.15,<0.3` (plus `langchain-openai>=0.2,<0.4`, matching the
  base range). **Verified by a clean-venv install** on Python 3.11.15:

  | package | version |
  |---|---|
  | ragas | 0.2.15 |
  | langchain | 0.3.30 |
  | langchain-core | 0.3.86 |
  | langchain-openai | 0.3.35 |
  | pydantic | 2.13.5 |
  | openai | 2.54.0 |

  `pip check` reports no broken requirements. All lazy imports the adapter uses
  (`SingleTurnSample`, `EvaluationDataset`, `Faithfulness`, `ResponseRelevancy`,
  `LLMContextPrecisionWithoutReference`, `LLMContextRecall`, `LangchainLLMWrapper`,
  `LangchainEmbeddingsWrapper`, `evaluate`, and `langchain_openai.ChatOpenAI` /
  `OpenAIEmbeddings`) resolve and construct.

- **Why this pin:** the adapter was written for the 0.2.x API (verified with
  0.2.15), which is compatible with the repo's `langchain>=0.3,<0.4`,
  `langchain-openai <0.4`, Pydantic v2 and Python 3.10+. The floor is the tested
  0.2.15 for reproducibility; the `<0.3` cap keeps an unreviewed API change from
  slipping in. RAGAS 0.4 is intentionally **not** adopted in this hardening pass.

- Metric-name mapping (project → RAGAS class → RAGAS column):
  `response_relevancy` maps to `ResponseRelevancy`, whose RAGAS column is
  `answer_relevancy`; the adapter normalises via each metric's `.name`.

- Metric-name mapping (project → RAGAS class):
  - `faithfulness` → `Faithfulness`
  - `response_relevancy` → `ResponseRelevancy` (formerly "answer relevancy")
  - `context_precision` → `LLMContextPrecisionWithoutReference`
  - `context_recall` → `LLMContextRecall` (**reference required**)

## Metrics implemented

Faithfulness, Response Relevancy, Context Precision (reference-free, run on all
cases), and Context Recall (run only on cases with a credible reference — 27 of
the 35 cases carry references; compensation and insufficient-evidence cases omit
them rather than fabricate). Optional RAGAS tool/agent metrics were **not**
included in this phase (the deterministic tool-selection benchmark stands).

## Case count

35 public cases across role responsibilities, skills, technologies, education,
compensation, labour-market, shortages, transition, digital competency,
cybersecurity, seniority, mixed, and insufficient-evidence — spanning US, UK,
Germany and EU/global.

## Compatibility verification (RAGAS-1A)

- **Optional extra installs:** `pip install -e ".[evaluation]"` succeeds in a
  clean Python 3.11 venv (versions above; `pip check` clean).
- **Base install still clean:** in the base venv (no `[evaluation]`), `import app`
  works and `ragas` is not present — the product runtime does not depend on RAGAS.
- **Offline integration tests pass both ways:**
  - RAGAS **absent** (base `.venv`): `pytest tests/test_ragas_adapter.py` → 16
    passed, 1 skipped (the installed-only import check skips).
  - RAGAS **installed** (clean venv): same file → 16 passed, 1 skipped (the
    missing-package check skips; the installed-import check runs).
  - Full suite with all extras incl. RAGAS: **1227 passed, 2 skipped** — same pass
    count as the base env, so RAGAS breaks nothing (Career Intelligence, Interview
    Practice, RAG Inspector, Evaluation, navigation, handoff, security all pass).
- **CLI with RAGAS installed but no credentials:** `python scripts/eval_ragas.py`
  and `--live` both print the NOT-RUN message and exit 0 — no traceback, no
  network call, no key required.

## Live evaluation run

**NO.** Implementation complete; live RAGAS baseline pending evaluator
credentials. In this environment RAGAS is not installed and `RAGAS_EVAL_API_KEY`
is not configured, so no live/paid run was performed and **no results are
fabricated**. The CLI and Evaluation page both report a clean NOT RUN.

To establish the baseline (small first, then full):

```bash
pip install -e ".[evaluation]"
export RAGAS_EVAL_API_KEY=...            # evaluator model key (not printed)
# export RAGAS_EVAL_BASE_URL=...  RAGAS_EVAL_MODEL=...   # optional
python scripts/eval_ragas.py --live --limit 10          # baseline sample
python scripts/eval_ragas.py --live                     # full set
```

Results are written to `evaluations/ragas/runs/<timestamp>/`
(`results.csv`, `results.json`, `summary.md`, `run_config.json`) and never
overwrite prior runs or any other historical evaluation artifact.

## Cost

Not applicable yet (no live run). Cost depends on the evaluator model and case
count; run the `--limit 10` baseline first to gauge it before the full set.

## What existing evaluations remain

All of them, unchanged and still primary: 11R, 11R-A, KB-2, product coverage,
quality_v2, faithfulness_v2, Hit@K / MRR / Recall@K, routing accuracy,
tool-selection accuracy, citation validity, provenance completeness,
insufficient-evidence checks, and the security/adversarial cases.

## Limitations

- No live baseline yet (needs evaluator credentials).
- RAGAS metrics are LLM-judged → cost and run-to-run variability; kept out of CI.
- Live runs also need a chat credential to generate answers; the generator and
  the evaluator are configured independently.
- First runs report **measured values, not pass/fail** — thresholds are only to be
  defined after a baseline exists, to avoid benchmark overfitting.

## Next steps

1. Configure `RAGAS_EVAL_API_KEY`; run the `--limit 10` baseline, then the full set.
2. Record the baseline and, only then, document candidate thresholds separately.
3. (Optional, experimental) evaluate safe tool-call traces with RAGAS tool metrics.
