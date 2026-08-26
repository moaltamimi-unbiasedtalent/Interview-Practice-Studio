# Rebuild the Knowledge Base

How to reproduce Career Intelligence's knowledge locally. No datasets are
committed; you acquire and build them here. All generated stores
(`data/knowledge/*.db`, `data/chroma/*`, `data/processed/*`) are git-ignored.

## 0. Check what is configured

```bash
python scripts/source_status.py
```

Shows a Knowledge Health summary and a per-source lifecycle table (measured from
what is on disk), then writes `data/source_status.json`. A source in the manifest
is **configured**, not necessarily loaded — the lifecycle badge (CONFIGURED →
… → AVAILABLE, plus MANUAL ACQUISITION / LICENCE REVIEW) tells you the real state.

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

Dispatches by filename (`roles_onet*`, `roles_esco*`, `isco*`, `kldb*`,
`bls_ooh*`) into `data/knowledge/roles.db`. Idempotent: re-ingesting an
occupation code replaces its rows.

## 3. Build the competency and labour-market stores

```bash
python scripts/load_competencies.py               # DigComp/NICE/e-CF/BA/OPM/Civil Service
python scripts/load_labour_market.py              # Cedefop forecast/openings/shortage
```

`load_competencies.py` fills `data/knowledge/competencies.db` (competencies,
proficiency levels, occupation–competency links, role behaviours by grade,
qualification requirements). `load_labour_market.py` fills
`data/knowledge/labour_market.db` (forecasts, openings, shortages). Both rebuild
their derived store each run. Dispatch is by filename prefix.

## 4. Build the compensation store

```bash
python scripts/load_compensation.py               # uses committed synthetic sample
python scripts/load_compensation.py --csv path/to/compensation.csv
```

Loads a CSV matching the compensation schema into
`data/knowledge/compensation.db` (rebuilt each run; a derived store). Context —
currency, pay period, statistic, geography, year — is preserved exactly.

## 5. Rebuild the narrative vector index

```bash
python scripts/ingest.py                  # data/raw → data/processed/chunks.jsonl
python scripts/rebuild_vector_index.py    # processed chunks → Chroma (with --reset)
```

Only narrative documents (methodology, reports, frameworks) are embedded;
structured role/competency/compensation/labour-market data is not.

## 6. Verify + evaluate

```bash
python scripts/source_status.py               # counts non-zero; regenerates source_status.json
python scripts/eval_rag.py                    # 11R baseline benchmark (unchanged)
python scripts/eval_expanded.py               # 11R-A expanded evaluation (unchanged)
python scripts/eval_knowledge_expansion.py    # KB-2 coverage/routing/geo (writes only under evaluations/knowledge_expansion/)
```

Then `streamlit run app.py` → the Knowledge Base page shows the Knowledge Health
dashboard and per-group lifecycle tables (Occupations, Skills & Competencies,
Seniority & Job Architecture, Compensation, Labour Market, Narrative, Specialist).

## Notes

- Prefer real, normalised extracts for production; the committed
  `evaluations/knowledge_samples/` are synthetic and only for a runnable demo.
- Embeddings: set `COPILOT_EMBEDDING_API_KEY` for semantic OpenAI embeddings;
  otherwise the offline local (lexical) embedder is used.
- Scripts fail safely and report what succeeded/failed; they never overwrite
  manually curated content unexpectedly.
