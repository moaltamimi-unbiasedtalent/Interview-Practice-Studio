# Rebuild the Knowledge Base

How to reproduce Career Intelligence's knowledge locally. No datasets are
committed; you acquire and build them here. All generated stores
(`data/knowledge/*.db`, `data/chroma/*`, `data/processed/*`) are git-ignored.

## 0. Check what is configured

```bash
python scripts/source_status.py
```

Shows every configured source, its authority, licence flag, whether it is
auto-downloadable or manual, and current structured/compensation record counts.

## 1. Download (auto sources only)

```bash
python scripts/download_sources.py
```

Fetches only sources the manifest marks directly downloadable and not licence-
blocked (e.g. O*NET, OEWS, ASHE, Eurostat). Manual sources (ESCO, ISCO, KldB,
Entgeltatlas, Cedefop, EQF, WEF) are listed for manual acquisition and never
scraped. Downloads land in `data/knowledge/downloads/` (git-ignored). Confirm
each source's licence before use — see [source_licensing.md](source_licensing.md).

## 2. Normalise structured role data

```bash
python scripts/normalise_roles.py                 # uses committed synthetic samples
python scripts/normalise_roles.py --source data/knowledge/raw   # your extracts
```

Dispatches by filename (`roles_onet*`, `roles_esco*`, `isco*`, `kldb*`) into
`data/knowledge/roles.db`. Idempotent: re-ingesting an occupation code replaces
its rows.

## 3. Build the compensation store

```bash
python scripts/load_compensation.py               # uses committed synthetic sample
python scripts/load_compensation.py --csv path/to/compensation.csv
```

Loads a CSV matching the compensation schema into
`data/knowledge/compensation.db` (rebuilt each run; a derived store). Context —
currency, pay period, statistic, geography, year — is preserved exactly.

## 4. Rebuild the narrative vector index

```bash
python scripts/ingest.py                  # data/raw → data/processed/chunks.jsonl
python scripts/rebuild_vector_index.py    # processed chunks → Chroma (with --reset)
```

Only narrative documents (methodology, reports, frameworks) are embedded;
structured role/compensation data is not.

## 5. Verify + evaluate

```bash
python scripts/source_status.py           # counts should now be non-zero
python scripts/eval_rag.py                # 11R baseline benchmark
python scripts/eval_expanded.py           # 11R-A expanded evaluation
```

Then `streamlit run app.py` → the Knowledge Base page shows the Role & Skill /
Compensation / Labour Market / Narrative sections populated.

## Notes

- Prefer real, normalised extracts for production; the committed
  `evaluations/knowledge_samples/` are synthetic and only for a runnable demo.
- Embeddings: set `COPILOT_EMBEDDING_API_KEY` for semantic OpenAI embeddings;
  otherwise the offline local (lexical) embedder is used.
- Scripts fail safely and report what succeeded/failed; they never overwrite
  manually curated content unexpectedly.
