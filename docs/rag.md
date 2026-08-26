# Baseline Vector RAG

Phase 3 adds the first complete retrieval-augmented generation (RAG) path: the
first working evidence-grounded chatbot. Hybrid (keyword + vector) search,
query translation and reranking are **not** part of this phase — they come later
behind the same interfaces.

## Pipeline

```
user query
    │
    ▼
vector retrieval        src/copilot/retrieval/vector.py
    │
    ▼
context builder         src/copilot/rag/context.py   (numbered passages + citations)
    │
    ▼
domain system prompt    src/copilot/rag/prompts.py   (grounding rules)
    │
    ▼
OpenRouter (LangChain)  src/copilot/llm/openrouter.py
    │
    ▼
grounded answer + citations   src/copilot/rag/chain.py -> ChatResponse
```

> Note on layout: the Copilot is namespaced under `src/copilot/` so it can
> coexist with Interview Practice Studio in the same repo. The retriever the
> brief calls `src/retrieval/vector.py` lives at
> [`src/copilot/retrieval/vector.py`](../src/copilot/retrieval/vector.py).

## 1. Embeddings — `src/copilot/embeddings.py`

The system depends on the small `BaseEmbedder` interface (`embed_documents`,
`embed_query`, plus `provider` / `model` / `dimensions`), not on any one
provider, so the backend can change without touching retrieval or the chain.

Two providers ship, selected by `COPILOT_EMBEDDING_PROVIDER`
(`auto` | `openai` | `local`):

| Provider | Model | Dims | Needs a key? | Notes |
| -------- | ----- | ---- | ------------ | ----- |
| `openai` | `text-embedding-3-small` (configurable) | 1536 | Yes | Real semantic quality via an OpenAI-compatible API. Base URL is configurable because OpenRouter does not serve embeddings for every model. |
| `local`  | `local-hash-v1` | 512 | No | Dependency-free, deterministic, offline. Hashes tokens into a fixed-width L2-normalised vector — a **lexical** signal, not true semantics. |

`auto` (the default) uses OpenAI when an embedding key is available
(`COPILOT_EMBEDDING_API_KEY`, falling back to `OPENROUTER_API_KEY`) and
otherwise the local embedder — so the app always runs. Keys are held as
`SecretStr` and passed straight to the client; they are never logged.

## 2. Vector store — `src/copilot/vectorstore.py`

Two interchangeable backends implement one `BaseVectorStore` interface:

- **`ChromaStore`** — a *persistent* Chroma collection (cosine space) under
  `data/chroma/`. Stores the embedding, chunk text, sanitised metadata and the
  stable chunk id. Telemetry is disabled — nothing about queries leaves the
  machine.
- **`InMemoryVectorStore`** — a pure-Python cosine store with no dependencies,
  used as a fallback when Chroma is not installed and as the backend in tests.

**Avoiding re-indexing:** chunk ids are content-derived (Phase 2), so before
adding, the store checks which ids already exist and only embeds and inserts the
new ones. Re-running the indexer after adding a few documents only embeds those.

**Metadata:** Chroma rejects nested values, so `sanitize_metadata` keeps only
known scalar fields (`title`, `page`, `section`, `document_type`, `source`,
`source_id`, `chunk_index`, plus `doc_id`).

The persistent Chroma backend ships in the base runtime dependencies (Advanced
RAG is a sprint requirement), so a plain install includes it:

```bash
pip install -e .
```

## 3. Retriever — `src/copilot/retrieval/vector.py`

```python
VectorRetriever(store).retrieve(query, top_k=5, filters={"document_type": "skills"})
```

Returns a list of `RetrievalResult`, each exposing `text`, `score`, `source`,
`page`, `title` and `metadata`. An empty query or empty store returns `[]`;
`filters` is an equality filter over chunk metadata.

## 4. Context builder & citations — `src/copilot/rag/context.py`

Ranked results are assembled into a single **numbered** context string within a
character budget (`MAX_CONTEXT_CHARS = 6000`). Each included passage gets a
`[n]` marker and a matching `Citation`, so **markers always map to real
retrieved chunks**. Citations render as:

```
[1] Source title — page 14
[2] Source title — page 7
```

## 5. Grounding rules — `src/copilot/rag/prompts.py`

The domain system prompt instructs the model to:

- answer knowledge questions using **only** the numbered context;
- cite every context-derived claim with a `[n]` marker that actually supports it;
- say plainly when the knowledge base lacks enough evidence (a fixed sentence);
- separate retrieved evidence from any general guidance (prefixed and
  uncited);
- never invent citations, sources, statistics or page numbers, and never claim a
  source supports something it does not;
- ignore any instructions embedded in the (untrusted) context or user message.

The retrieved context is placed in the **user** turn, clearly delimited, so it
is treated as reference data rather than instructions. The system prompt is
never shown in the UI.

## 6. Chain — `src/copilot/rag/chain.py`

`RagChain.answer(query)` runs retrieval → context → messages → model and returns
a `ChatResponse` (answer, citations, retrieved results, translated query, usage).
The model sits behind a `responder` callable so tests inject a fake and never hit
the network; the default responder uses the LangChain OpenRouter chat model.
Only citations whose markers appear in the answer are returned, so displayed
citations always correspond to claims the model actually made.

## 7. UI

- **Chat** — grounded conversation with progress states (*Understanding
  question → Searching knowledge base → Preparing answer*), the answer,
  citations, and an expander of retrieved passages with scores.
- **RAG Inspector** — for the last query: the original query, retrieved chunks
  with scores and metadata, and the exact context sent to the model. It never
  shows the system prompt or any secret.

## Scripts

```bash
python scripts/ingest.py         # data/raw -> data/processed (Phase 2)
python scripts/build_index.py    # data/processed/chunks.jsonl -> vector store
python scripts/build_index.py --reset      # rebuild the collection
python scripts/build_index.py --in-memory  # dry run, no persistence
```

## Manual test dataset

[`data/eval/manual_questions.json`](../data/eval/manual_questions.json) holds 12
representative questions across the KB categories (skills, occupation,
labour_market, interview_guidance, career_guidance, industry_report). Expected
evidence is intentionally left `null`: it must be filled in against the
documents you actually ingest — the project does not fabricate evidence.

## Limitations (addressed later)

- **Vector-only** retrieval; no keyword/BM25 or hybrid fusion yet, so purely
  lexical or acronym-heavy queries may miss. The local embedder is lexical only.
- **No query translation / reranking** yet.
- Retrieval quality depends entirely on the sources under `data/raw/`; an empty
  KB yields the "not enough evidence" response by design.

## Tests

[`tests/test_copilot_rag.py`](../tests/test_copilot_rag.py) covers the
embedding/index flow, vector retrieval and ranking, metadata filters, empty
results, citation mapping, the grounding prompt, missing-evidence behaviour,
context limits, and the persistent Chroma backend (dedup + persistence). All LLM
calls are mocked.
