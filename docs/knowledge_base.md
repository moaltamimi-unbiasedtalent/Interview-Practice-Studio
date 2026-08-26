# Knowledge Base & Document Ingestion

This document describes the knowledge-base ingestion layer for the Career
Intelligence Copilot: where source documents come from, how they are loaded,
cleaned, chunked, and indexed, and the current limitations. Advanced retrieval
(embeddings, vector store, hybrid search, reranking) is **not** part of this
layer and is built in a later phase.

> **Scope note.** This document covers the **vector/narrative** layer only. Career
> Intelligence is a multi-source system: structured data (occupations, skills,
> competencies, compensation, labour-market) lives in SQLite stores, not the
> vector index. For the full 25-source picture, the store routing and the measured
> source lifecycle, see [knowledge_architecture.md](knowledge_architecture.md) and
> [knowledge_source_catalogue.md](knowledge_source_catalogue.md).

## Source strategy

The Copilot is designed to give **grounded** career guidance — every answer
should be traceable to real evidence rather than model recall. Source documents
therefore come from reputable, citable career and labour-market publications.

Documents live under `data/raw/`, organised into category subfolders. The
folder name sets each document's `document_type` metadata. Recognised
categories (`src/copilot/constants.py::KNOWN_DOCUMENT_TYPES`):

| Category             | What it holds                                        | Example sources                     |
| -------------------- | ---------------------------------------------------- | ----------------------------------- |
| `labour_market`      | Employment outlook, demand, wages, trends            | WEF Future of Jobs, BLS, Eurostat   |
| `occupation`         | Role definitions, tasks, day-to-day duties           | O\*NET, ESCO occupation profiles    |
| `skills`             | Skill taxonomies, competencies, skill demand         | ESCO skills, LinkedIn skills reports |
| `career_guidance`    | Career-planning and progression advice               | Government careers services         |
| `interview_guidance` | Interview preparation, question banks, frameworks    | STAR method guides, question banks  |
| `industry_report`    | Sector deep-dives and analyses                       | Industry / consultancy reports      |

Anything placed outside a recognised subfolder is tagged `uncategorized`.

**Do not fabricate data.** The repository ships with an empty `data/raw/` (only
its `README.md` and a `.gitkeep` are tracked). Real source files, the generated
vector store, and processed outputs are intentionally git-ignored so the
repository stays free of large or licence-encumbered content. See
[`data/raw/README.md`](../data/raw/README.md) for how to add sources, per-file
sidecar metadata, and CSV column configuration.

## Ingestion pipeline

```
discover → load → clean → chunk → dedup → report → (persist)
```

Run it with the CLI:

```bash
python scripts/ingest.py                       # ingest data/raw, write processed outputs
python scripts/ingest.py --no-write            # report only, write nothing
python scripts/ingest.py --csv-content-columns title,description \
                         --csv-metadata-columns occupation,year
```

The CLI prints an ingestion report (documents, chunks, duplicates, per-type
counts, errors) and, unless `--no-write` is given, writes processed outputs to
`data/processed/`. The **Knowledge Base** page in `copilot_app.py` reads the
manifest and shows the same statistics.

### 1. Discover — `indexer.discover_documents`

Recursively walks `data/raw/`, returning supported files sorted for
determinism. Skips `README.md`, `.gitkeep`, and `*.meta.json` sidecars.
Supported extensions: `.pdf`, `.txt`, `.md`, `.markdown`, `.csv`.

### 2. Load — `ingestion/loaders.py`

Each file is turned into one or more `LoadedUnit`s (text + metadata). Every unit
records `filename`, `title`, `document_type`, `source`, and, where applicable,
`page` or `section`.

- **PDF** (`pypdf`) — one unit per page, with a 1-based `page` number. Blank
  pages are skipped; a malformed PDF raises `LoaderError` (caught per file, so
  one bad file never aborts the run).
- **Markdown** — split into sections on `#` headings; each section records its
  heading as `section`.
- **Text** — the whole file as a single unit.
- **CSV** (`pandas`) — one unit per row. `content_columns` are joined as
  `"column: value"` lines to form the text; `metadata_columns` are copied into
  metadata. With no columns specified, all columns become content.

Document type is inferred from the parent folder name, overridable per file via
a `<file>.meta.json` sidecar or the `document_type` argument. Unsupported
extensions raise `LoaderError`.

### 3. Clean — `ingestion/cleaners.py`

`clean_text` is deliberately **conservative** — it removes noise without
altering meaning, so headings, punctuation, and lists survive intact:

- normalises line endings to `\n`;
- strips zero-width characters and converts non-breaking spaces to spaces;
- trims trailing whitespace on each line;
- collapses runs of 2+ spaces to one;
- collapses 3+ consecutive blank lines to a single blank line.

### 4. Chunk — `ingestion/chunking.py`

Cleaned units are split with LangChain's `RecursiveCharacterTextSplitter`
(separators `["\n\n", "\n", ". ", " ", ""]`) so breaks fall on natural
boundaries. Defaults (`constants.py`): `CHUNK_SIZE = 1000`,
`CHUNK_OVERLAP = 150` characters — large enough to preserve context, small
enough for precise retrieval later. Each chunk becomes a `DocumentChunk` whose
metadata carries the originating unit's fields plus `source_id` and
`chunk_index`.

### 5. Stable ids & deduplication

- **File-level:** `source_id_for_bytes` hashes the raw file bytes, so
  re-ingesting an identical file is skipped (`skipped_duplicate_files`).
- **Chunk-level:** each `chunk_id` is `sha256(source_id :: chunk_text)`
  truncated to `ID_HASH_LENGTH` (16 hex chars). Ids are therefore content-
  derived and reproducible, and duplicate chunks within a document are dropped.

This makes ingestion **idempotent**: the same inputs always yield the same ids,
so re-runs never create duplicates.

### 6. Report & persist — `ingestion/indexer.py`

`IngestionReport` collects safe-to-display statistics (counts, per-type
breakdown, per-document rows, errors) — never raw document content.
`write_processed` persists:

- `data/processed/chunks.jsonl` — one `DocumentChunk` per line;
- `data/processed/manifest.json` — the report, read by the UI.

## Data files & privacy

- `data/raw/` and `data/processed/` are git-ignored except for structure files
  (`README.md`, `.gitkeep`). Source documents and processed outputs are never
  committed.
- The ingestion report and the Knowledge Base UI expose only statistics, never
  the text of source documents.
- No embeddings and no network calls happen during ingestion.

## Limitations (addressed in later phases)

- **No retrieval yet** — no embeddings, no vector store, no search. This layer
  only produces clean, chunked, deduplicated text with metadata.
- **PDF extraction is text-only** — scanned/image PDFs need OCR (not included);
  complex tables and multi-column layouts may extract imperfectly.
- **Chunking is character-based**, not token-aware; sizes are approximate for
  any specific embedding model.
- **Section detection** is heading-based for Markdown only; plain PDFs/TXT are
  chunked without semantic section boundaries.

## Tests

`tests/test_copilot_ingestion.py` covers cleaning, every loader (text,
markdown, CSV, and a real PDF generated with `fpdf2`), document-type inference,
unsupported types, chunk boundaries, deterministic ids, within-document dedup,
duplicate-file handling, malformed PDFs, empty documents, and the
manifest write/load round-trip.
