# RAGAS implementation report (PHASE RAGAS-1)

## Summary

Added RAGAS as an **optional, secondary** generation-quality evaluation layer for
Career Intelligence. The existing deterministic evaluation (11R, 11R-A, KB-2,
product coverage, quality_v2, faithfulness_v2) is unchanged and remains the
primary CI quality gate.

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

- Pinned `ragas>=0.2,<0.3` (plus `langchain-openai>=0.2,<1.0`) — the modern RAGAS
  API: `SingleTurnSample`, `EvaluationDataset`, metric classes, and `evaluate()`
  with `LangchainLLMWrapper` / `LangchainEmbeddingsWrapper`.
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
