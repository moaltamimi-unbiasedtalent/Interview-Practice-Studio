# Expanded Career Intelligence — Evaluation (11R-A)

Phase 11R established the initial RAG benchmark (preserved in `retrieval_results.csv` / `rag_evaluation.md`). This 11R-A report measures the expanded multi-lane architecture and compares core retrieval to that baseline. 11R artifacts are unchanged.

## Routing accuracy
- Overall: **1.0** (10/10)
- By lane: structured_role=1.0, compensation=1.0, forecast=1.0, vector=1.0, mixed=1.0

## Structured role retrieval
- Hit rate: **1.0** · provenance completeness: **1.0** · latency: 0.03 ms

## Compensation retrieval
- Accuracy (country+year+currency+statistic+source): **1.0** · provenance completeness: **1.0**

## Core retrieval vs 11R baseline

| mode | hit@k | mrr | recall@k | Δ hit | Δ mrr | Δ recall |
|---|---|---|---|---|---|---|
| vector | 0.97 | 0.842 | 0.955 | 0.0 | 0.0 | 0.0 |
| keyword | 0.97 | 0.904 | 0.97 | 0.0 | 0.0 | 0.0 |
| hybrid | 0.939 | 0.871 | 0.924 | 0.0 | 0.0 | 0.0 |

## Findings & limitations
- The expanded architecture ADDS lanes; it does not change narrative vector retrieval, so core hit@k/MRR/recall are expected to match the baseline (Δ ≈ 0). Improvement is in **coverage**: structured role and compensation questions that vector RAG could not answer precisely are now served by dedicated lanes with provenance.
- Numbers reflect the committed synthetic samples; real datasets refine them.
- Regressions, if any, are shown in the Δ columns and are not hidden.
