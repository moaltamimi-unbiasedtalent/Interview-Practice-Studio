# Career Intelligence — RAG Evaluation

Dataset: **33 cases**, top_k=**5**, over a committed corpus of **14 documents** (`evaluations/corpus/`).
Embedder: **local/local-hash-v1**. Translator: **heuristic (offline)**. This run is deterministic and free; see caveats below.

## 1. Retrieval strategies (vector / keyword / hybrid)

| mode | Hit@5 | MRR | Recall@5 | TermRecall@5 | Latency (ms) |
|---|---|---|---|---|---|
| vector | 0.97 | 0.842 | 0.955 | 0.97 | 0.389 |
| keyword | 0.97 | 0.904 | 0.97 | 0.97 | 0.022 |
| hybrid | 0.939 | 0.871 | 0.924 | 0.939 | 0.432 |

Best by MRR then Hit@5: **keyword**.

## 2. Query-translation experiment

| query | Hit@5 | MRR | Recall@5 | Latency (ms) |
|---|---|---|---|---|
| original | 0.939 | 0.871 | 0.924 | 0.424 |
| translated | 0.939 | 0.871 | 0.924 | 0.428 |

> Translation ran with the **offline heuristic** translator, which returns the original query with no alternates — so 'translated' equals 'original' here. This is reported honestly: no translation effect is measurable offline. Re-run with an LLM translator to measure the semantic effect. We do **not** assume translation is better.

## 3. Tool selection

Accuracy: **1.0** (6/6 cases).

| id | expected | selected | correct |
|---|---|---|---|
| tool_01 | job_description_analyzer | job_description_analyzer | True |
| tool_02 | job_description_analyzer|candidate_gap_analyzer | job_description_analyzer|candidate_gap_analyzer | True |
| tool_03 | job_description_analyzer|candidate_gap_analyzer|preparation_plan_calculator | job_description_analyzer|candidate_gap_analyzer|preparation_plan_calculator | True |
| tool_04 | interview_question_generator | interview_question_generator | True |
| tool_05 | — | — | True |
| tool_06 | — | — | True |

## 4. Citation correctness

- Cases considered: 33
- Citation ids map to retrieved chunks: **1.0**
- Cited source exists (title/source present): **1.0**

Citations are constructed from the retrieved passages, so by design every marker maps to a real retrieved chunk; this check validates that invariant.

## 5. Honest caveats

- The **local hashing embedder** is lexical, not semantic, so vector numbers understate what OpenAI embeddings would achieve; hybrid/keyword benefit on exact-term probes. Re-run with `COPILOT_EMBEDDING_API_KEY` for semantic vector.
- The corpus is a small **synthetic** set of general career facts for a reproducible benchmark; absolute numbers reflect that corpus.
- We do **not** rewrite results to favour hybrid. If hybrid does not win on a metric, the table shows it; likely reasons: a lexical embedder narrows the gap between vector and keyword, and single-source questions cap Recall@k.
