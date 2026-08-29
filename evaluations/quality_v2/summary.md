# Quality v2 — held-out evaluation

Generated 2026-08-29T18:41:45Z · embedding **OFFLINE LEXICAL** · top_k=5.
Held-out set authored after build; deterministic + offline; 11R/11R-A untouched.

## Held-out retrieval (hybrid, lexical)

- Hit@5: **0.917** · MRR: **0.704** · Recall@5: **0.917** · term-recall: 1.0 (12 cases)

## Tool selection

- Accuracy: **1.0** over 6 known-intent cases.

## Out-of-domain separation (lexical query-content overlap)

- In-domain overlap mean: 0.669 (min 0.167); OOD overlap mean: 0.0.
- OOD leaks at in-domain min: **0** / 3.

## Faithfulness

- Present: see `evaluations/faithfulness_v2/` (run `python scripts/eval_faithfulness_v2.py`).

## LLM-judge

- NOT RUN — LLM-judge is optional and disabled by default; it requires a chat credential and is never run in CI.

