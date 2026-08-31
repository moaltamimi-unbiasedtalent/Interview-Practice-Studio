# RAGAS evaluation cases (public, held-out)

`cases.json` holds public Career Intelligence questions for the **optional**
RAGAS generation-quality layer. See [`docs/ragas_evaluation.md`](../../docs/ragas_evaluation.md).

- **Public data only** — no candidate backgrounds, job descriptions, transcripts,
  or company files. Questions are generic across professions and geographies
  (US / UK / Germany / EU-global).
- Each case has a `question`, `category`, `geography`, and `expected_source_family`.
  A short factual `reference` is included where practical (derived from public
  official career sources); it is **omitted, never fabricated**, for cases whose
  ground truth is a specific figure (compensation) or which are deliberately
  out-of-domain (insufficient-evidence). Context Recall runs only where a
  reference exists.
- Answers and retrieved contexts are **generated at live-run time** by running
  Career Intelligence — they are not stored here.

## Running

```bash
# Without evaluator credentials → clean NOT RUN, exit 0:
python scripts/eval_ragas.py

# Live (requires RAGAS_EVAL_API_KEY; and a chat credential to generate answers):
python scripts/eval_ragas.py --live --limit 10     # small baseline first
python scripts/eval_ragas.py --live                # full set
```

Results are written to `evaluations/ragas/runs/<timestamp>/` and never overwrite
prior runs or any other historical evaluation artifact.
