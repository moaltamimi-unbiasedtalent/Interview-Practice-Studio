# Retrieval Quality v2

Generated 2026-08-29T10:38:04Z · corpus `evaluations/corpus` (fp 39c76496afba8b1f) · dataset `evaluations/rag_dataset.json`.
Embedding: **OFFLINE LEXICAL** (local/local-hash-v1).

> SEMANTIC EVALUATION NOT RUN — CREDENTIAL NOT CONFIGURED. Set COPILOT_EMBEDDING_API_KEY (and COPILOT_EMBEDDING_PROVIDER=openai) then re-run: python scripts/eval_retrieval_quality_v2.py

Does not modify 11R / 11R-A artifacts.

## Offline (lexical) runs

| Config | Mode | Hit@K | MRR | Recall@K | chunks |
|---|---|---|---|---|---|
| 1_localhash_baseline | vector | 0.97 | 0.842 | 0.955 | 14 |
| 1_localhash_baseline | keyword | 0.97 | 0.904 | 0.97 | 14 |
| 1_localhash_baseline | hybrid | 0.939 | 0.871 | 0.924 | 14 |
| 3b_localhash_section | hybrid | 0.939 | 0.871 | 0.924 | 14 |

## Semantic runs — NOT RUN (no credential)

- 2_semantic_baseline
- 3_semantic_section
- 4_semantic_hybrid
- 5_semantic_hybrid_reranker
