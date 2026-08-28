# Rebuild the Knowledge Base

How to reproduce Career Intelligence's knowledge locally. No datasets are
committed; you acquire and build them here. All generated stores
(`data/knowledge/*.db`, `data/chroma/*`, `data/processed/*`) and the raw corpus
(`data/raw/*`) are git-ignored.

## Local-first (preferred)

If the real source files are already under `data/raw/`, build everything from
them — no downloads:

```bash
python scripts/inventory_sources.py       # inventory data/raw → source_inventory.json + docs/local_source_inventory.md
python scripts/load_local_sources.py      # roles.db (O*NET/ESCO/ISCO/KldB) + compensation.db (OEWS/ASHE) from real files
python scripts/load_competencies.py       # competency frameworks (DigComp/NICE/e-CF/BA/OPM/Civil Service)
python scripts/load_labour_market.py      # Cedefop forecast/openings/shortage
python scripts/ingest_local_narrative.py  # index narrative PDFs (WEF/ESCO handbook/EQF/OPM/Civil Service/NICE/…) into Chroma
python scripts/source_status.py           # measured lifecycle + source_status.json
python scripts/knowledge_coverage.py      # docs/knowledge_coverage_report.md
python scripts/final_source_report.py     # docs/local_source_report.md (exact counts)
```

The inventory identifies each raw file's source/version/geography and maps it to
the manifest; the loaders read those files in place (nothing is moved or renamed).
`ingest_local_narrative.py` vectorises **only** narrative PDFs — structured tables
(occupations, salaries, matrices) are never embedded — and tags each chunk with
its manifest `source_id` + `source_url` so citations link back.

> Embeddings offline: an `OPENROUTER_API_KEY` is a chat key, not an embeddings
> key. With no dedicated `COPILOT_EMBEDDING_API_KEY`, the app uses the offline
> local (lexical) embedder for both indexing and retrieval, so everything works
> without an embeddings provider.

The steps below are the generic acquisition path when files are **not** already
local.

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
