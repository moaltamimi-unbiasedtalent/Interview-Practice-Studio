# Advanced Query Translation

Phase 4 inserts a **query-understanding stage** between the user and vector
retrieval. User queries are no longer sent straight to the retriever: they are
classified, rewritten, expanded into several retrieval queries, and given safe
metadata filters — then the results are fused. This is a core assignment
requirement and is fully visible in the **RAG Inspector**.

```
user query
    │
    ▼
query translation      src/copilot/rag/translation.py
  · intent classification
  · retrieval-needed decision
  · query rewriting
  · multi-query generation (2–4)
  · safe metadata filters
    │
    ▼
retrieval per query    src/copilot/retrieval/vector.py
    │
    ▼
reciprocal-rank fusion src/copilot/retrieval/fusion.py   (merge + dedup)
    │
    ▼
context → grounding prompt → OpenRouter → grounded answer
```

## 1. Query classification & retrieval decision

The translator classifies each query into one intent
(`constants.QUERY_INTENTS`):

`factual_career`, `role_research`, `skill_research`,
`job_description_analysis`, `candidate_comparison`, `preparation_planning`,
`interview_preparation`, plus `smalltalk` / `other`.

It also decides `retrieval_required`. Small talk and greetings skip the
knowledge base entirely (`NO_RETRIEVAL_INTENTS`), so the chain does not retrieve
and the model just responds conversationally.

## 2. Query rewriting

An ambiguous query is rewritten into a clearer retrieval query **without adding
facts** and **preserving intent**:

```
What should I learn for AI?
    ->
Skills, technical competencies and knowledge required for AI engineering roles
```

## 3. Multi-query generation

For broad questions the translator emits 2–4 retrieval variants covering
different angles:

```
AI engineer technical skills
AI engineering role competencies
future demand for AI skills
```

Alternates are de-duplicated (and never repeat the rewritten query), capped at
`MAX_ALTERNATE_QUERIES`.

## 4. `TranslatedQuery` (Pydantic-validated)

Defined in [`src/copilot/models.py`](../src/copilot/models.py):

| Field | Meaning |
| ----- | ------- |
| `original_query` | the user's text |
| `rewritten_query` | the single clearer retrieval query |
| `alternate_queries` | 0–N extra retrieval variants |
| `intent` | classified intent (validated against the allowed set) |
| `retrieval_required` | whether to search the knowledge base |
| `metadata_filters` | safe, whitelisted equality filters |
| `explanation` | one short, user-safe sentence — **no chain-of-thought** |
| `strategy` | `llm` / `heuristic` / `passthrough` / `fallback` provenance |

The LLM is prompted to return **strict JSON only**; the output is parsed and
validated into this model.

## 5. Retrieval fusion (RRF)

Each translated query is retrieved independently, then the ranked lists are
merged with **Reciprocal Rank Fusion**
([`src/copilot/retrieval/fusion.py`](../src/copilot/retrieval/fusion.py)):

```
fused_score(chunk) = Σ over lists  1 / (k + rank)      (k = 60)
```

Duplicate chunks (same `chunk_id`) are merged, ties break deterministically by
id, and the top-k are returned. This rewards chunks that rank well across
queries and never simply concatenates the lists.

## 6. Safe, structured metadata filters

The LLM may *suggest* filters, but only whitelisted equality filters ever reach
the store. `sanitize_filters` keeps only fields in
`constants.ALLOWED_FILTER_FIELDS` (currently `document_type`, restricted to the
known categories) and drops everything else:

```python
{"document_type": "occupation", "hacked": "1=1"}  ->  {"document_type": "occupation"}
```

The LLM never constructs query code — it only proposes field/value pairs that are
validated against the whitelist before use. Only fields actually present in the
index are allowed.

## 7. Robust fallback

Translation must never break the chat. If there is no model configured, the LLM
raises, or the output is malformed/invalid JSON, the translator returns a
deterministic `heuristic_translation` (keyword-based intent, the query used
as-is, safe default filters). The `strategy` field records which path was taken.

## 8. RAG Inspector

For the last query the inspector shows the original query, the intent and
retrieval decision, the rewritten query, the alternative queries, the metadata
filters, the short explanation, and the retrieved/fused chunks with scores and
context. System prompts and secrets are never shown.

## Tests

[`tests/test_copilot_translation.py`](../tests/test_copilot_translation.py)
covers simple / ambiguous / broad / role / no-retrieval queries, multi-query
de-duplication and fusion, filter sanitisation (including injection-style
attempts), malformed translation, and the fallback when the model errors. The
translation LLM is mocked with canned JSON.
