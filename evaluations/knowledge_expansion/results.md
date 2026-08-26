# Knowledge Expansion Evaluation (KB-2)

Offline, deterministic evaluation of the expanded authoritative career knowledge system. Does not modify the preserved 11R / 11R-A baseline artifacts.

## Coverage (measured)

- Configured sources: **25**
- Available for retrieval (loaded locally): **16**
- Acquired on disk: **16**
- Manual acquisition required: **17**
- Licence review required: **15**
- Structured records loaded: **53**

Per-source lifecycle in `coverage.csv`.

## Routing accuracy

- Lane routing accuracy: **100%** (12/12)
- Geographic precedence accuracy: **100%** (4/4)

Per-case detail in `routing_results.csv` and `geo_results.csv`.

## Provenance

Every structured record carries a `source_id` by schema; every manifest source without a resolved licence is flagged for review or manual acquisition (verified in `tests/test_knowledge_expansion.py`).

## Method

- Routing: deterministic router over labelled cases (no LLM).
- Coverage/lifecycle: measured from local structured stores and the vector manifest — a configured source is never assumed loaded.
- No network or paid LLM calls.
