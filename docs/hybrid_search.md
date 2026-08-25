# Hybrid Search (vector + BM25)

Phase 5 implements the first **hard** optional requirement: hybrid retrieval that
combines semantic (vector) and lexical (BM25) search. Vector retrieval is
retained in full — hybrid only *adds* a lexical channel and fuses the two.

```
query
 ├─ vector search   (semantic / conceptual)      src/copilot/retrieval/vector.py
 └─ BM25 search     (exact terms, acronyms)       src/copilot/retrieval/keyword.py
        ↓
  reciprocal-rank fusion (weight-configurable)     src/copilot/retrieval/fusion.py
        ↓
  deduplicate + top-k                              src/copilot/retrieval/hybrid.py
```

> Layout note: the Copilot is namespaced under `src/copilot/`, so the modules the
> brief calls `src/retrieval/keyword.py` and `src/retrieval/hybrid.py` live at
> [`src/copilot/retrieval/keyword.py`](../src/copilot/retrieval/keyword.py) and
> [`src/copilot/retrieval/hybrid.py`](../src/copilot/retrieval/hybrid.py).

## Why hybrid for career / job data

Career and job content is full of **exact tokens** that carry precise meaning and
must match literally:

- programming languages and tools — `Python`, `SQL`, `SAP`
- standards and certifications — `ISO 27001`, `CIPD`, `SHRM`, `PMP`
- specific job titles — `DevOps engineer`, `site reliability engineer`

A pure semantic embedder can drift from these to *related* concepts (e.g. "SQL"
→ generic "databases", "CIPD" → generic "HR training"), which is exactly wrong
when a user is screening for a named skill or credential. BM25 matches the token
itself, so it nails these queries.

Conversely, many career questions are **conceptual** — "what capabilities matter
for senior leadership?", "how is automation reshaping work?" — where the exact
words may never appear and semantic similarity is what finds the right passage.

Hybrid keeps both strengths: BM25 for precise terms, vectors for concepts.

## 1. BM25 — `keyword.py`

`KeywordRetriever` builds a `rank_bm25.BM25Okapi` index over the **same chunks**
held by the vector store (`KeywordRetriever.from_store(store)` uses
`store.all_chunks()`), preserving each chunk's metadata. A shared tokeniser
(`tokenize`) lower-cases and splits on alphanumerics for both documents and
queries, so `"ISO 27001"` indexes and matches as `["iso", "27001"]`. Results are
returned as the same `RetrievalResult` type (`retriever="keyword"`), filtered to
`score > 0` and to any metadata filter. If `rank-bm25` is not installed the
channel degrades to empty results (hybrid then behaves as vector-only) rather
than crashing.

## 2. Hybrid retriever — `hybrid.py`

`HybridRetriever` runs both channels (each over a candidate pool of
`HYBRID_CANDIDATE_K`, ≥ the final `top_k`, so a result strong in only one channel
can still surface), then fuses. `search()` returns a `HybridSearch` exposing the
`vector`, `keyword` and `fused` lists for the inspector; `retrieve()` returns the
fused top-k and is interchangeable with the other retrievers.

## 3. Fusion — Reciprocal Rank Fusion

We fuse with **RRF**, not a blend of raw scores:

```
fused_score(chunk) = Σ over channels  weightᵢ / (k + rankᵢ)      (k = 60)
```

Why RRF:

- Vector **cosine similarities** and **BM25 scores** live on different,
  incomparable scales; averaging them is meaningless without fragile
  normalisation. RRF combines *ranks*, which is scale-free and explainable.
- It is deterministic (ties break by chunk id) and easy to reason about in a
  project review.

**Weights are configurable but default to equal** (`HYBRID_VECTOR_WEIGHT =
HYBRID_KEYWORD_WEIGHT = 1.0`, overridable via `COPILOT_HYBRID_VECTOR_WEIGHT` /
`COPILOT_HYBRID_KEYWORD_WEIGHT`). We deliberately avoid arbitrary weighting: no
channel is favoured without evidence from evaluation on the actual corpus.

The same fusion also merges the multi-query lists from Phase 4, so duplicate
chunks are merged exactly once across everything.

## 4. Retriever selection

`build_retriever(config, mode=...)` supports `vector`, `keyword` and `hybrid`,
with **hybrid as the default** (`config.retrieval_mode`, env
`COPILOT_RETRIEVAL_MODE`). The single-channel modes are kept for testing and
evaluation. The sidebar in the app switches modes live; all three share one
vector store so vector and BM25 index the same chunks.

## 5. RAG Inspector

For the last query the inspector shows the retrieval mode and, in hybrid mode,
the **vector hits**, **keyword/BM25 hits**, the **fused ranking**, and the
**final result set** — with per-channel scores (labelled as not directly
comparable).

## 6. Evaluation baseline

`scripts/eval_retrieval.py` and the **Evaluation** page compare the three modes
over probes in
[`data/eval/retrieval_probes.json`](../data/eval/retrieval_probes.json) using
`src/copilot/evaluation/retrieval_eval.py`.

The metrics are **lexical proxies** — `term_recall@k` (did a top-k chunk contain
an expected exact term?), `coverage`, `avg_results`. They characterise
exact-term behaviour on the probes; they do **not** establish overall semantic
relevance, which would need human relevance judgements. **We do not claim hybrid
wins** — run the comparison on your own ingested corpus and draw conclusions only
from labelled evaluation. Expect BM25/hybrid to help the exact-term probes
(`Python`, `SAP`, `SQL`, `ISO 27001`) while vector retains the conceptual ones.

## Setup

BM25 lives in the `rag` extra:

```bash
pip install -e ".[rag]"
```

## Tests

[`tests/test_copilot_hybrid.py`](../tests/test_copilot_hybrid.py) covers semantic
queries, exact keywords, acronyms, rare technology codes, fusion de-duplication,
score fusion, configurable weights, retriever selection, corpus round-trip, and
the evaluation baseline.
