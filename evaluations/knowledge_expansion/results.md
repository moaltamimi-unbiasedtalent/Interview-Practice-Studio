# Knowledge Expansion Evaluation (KB-2)

Offline, deterministic evaluation of the expanded authoritative career knowledge system. Does not modify the preserved 11R / 11R-A baseline artifacts.

## Coverage (measured)

- Configured sources: **29**
- Available for retrieval (loaded locally): **26**
- Acquired on disk: **27**
- Manual acquisition required: **2**
- Licence review required: **2**
- Structured records loaded: **15211**

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
