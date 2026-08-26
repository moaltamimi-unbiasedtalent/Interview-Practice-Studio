# Career Intelligence Copilot — Project Plan

**Sprint:** Building Applications with AI (Turing College)
**Tagline:** Grounded career guidance, job analysis and interview preparation using real evidence.

> **Repository note.** Career Intelligence Copilot is the **evolution of this
> repository**, not a separate project. Work happens on
> `feature/career-intelligence-copilot` and each phase is merged into `main`
> (the repo's mainline). `main` already hosts the earlier **Interview Practice
> Studio** product, which provides proven, reusable infrastructure (see "Reuse"
> below) that this product builds on.

---

## 1. Problem statement

Career advice online is generic, opinion-driven and rarely cited. Candidates
cannot easily tell *why* a piece of guidance applies to them, which skills a
specific role truly requires, or where they fall short. **Career Intelligence
Copilot** answers career and interview questions with **grounded, cited**
evidence retrieved from a curated knowledge base, and turns a job description +
a candidate's background into concrete, evidence-linked next steps.

## 2. Target users

- **Job seekers / career changers** — understand a role and prepare for it.
- **Students / early-career** — learn what a field expects and how to close gaps.
- **Coaches / career services** — a grounded assistant with visible sources.

It is a **guidance and preparation** tool, not a hiring/assessment system, and
never presents outputs as objective hiring decisions.

## 3. Use cases

1. Ask a career question and get a grounded, cited answer.
2. Analyse a pasted job description → required skills, seniority, themes.
3. Compare a candidate background against a role → strengths and **skill gaps**.
4. Generate a **preparation plan** (prioritised, time-boxed).
5. Generate **role-specific interview questions**.
6. Retrieve supporting evidence from the knowledge base with **citations**.
7. Inspect the RAG process: query translation, retrieved chunks, which **tools**
   were called, and token/cost usage.

## 4. Architecture (proposed)

```
Streamlit UI (app.py)
  │  chat · sources/citations · retrieved context · tool calls · progress · usage
  ▼
Chat orchestrator  (src/rag/chain.py — LangChain + OpenRouter)
  ├── Security: input_guard + injection_guard (reuse src/security.py)
  ├── Query translation (multi-query / HyDE / decomposition)
  ├── Hybrid retrieval:  vector (Chroma) ⊕ keyword (rank-bm25)  → fusion → reranker
  ├── Context builder + citations + grounding checks
  ├── Tool calling (4 tools, Pydantic-typed)
  └── Usage/cost tracker
Offline: ingestion pipeline  (loaders → cleaners → chunking → embeddings → Chroma + BM25)
```

Design rules (carried from the existing codebase): UI renders only; logic lives
in `src/`; constants centralised; config via secrets→env with no default key and
controlled missing-config; Pydantic validation at the edges; no secret ever
logged/committed.

## 5. Data flow

**Ingestion (offline, `scripts/ingest.py`):**
raw docs (`data/raw/`) → load (PyPDF/text/markdown) → clean/normalise → chunk
(with metadata: source, title, section, page) → embed → persist to Chroma
(`data/chroma/`) + build BM25 index. Processed artefacts in `data/processed/`.

**Query time:**
user query → input/injection guard → query translation (expand/rewrite) →
hybrid retrieval (vector + BM25) → fusion (e.g. Reciprocal Rank Fusion) →
optional rerank → context builder (dedupe, budget, attach citations) →
LLM (OpenRouter via LangChain) with tools → grounded, cited answer →
usage/cost recorded; UI shows sources, tool calls and progress.

## 6. RAG architecture

- **Knowledge base:** curated career/labour-market/interview evidence (role
  profiles, skills taxonomies, interview guides, labour-market summaries). Stored
  in `data/raw/`; provenance tracked in metadata.
- **Chunking:** structure-aware, overlapping chunks with rich metadata for
  filtering and citation.
- **Embeddings:** OpenAI-compatible embeddings via OpenRouter/compatible SDK;
  model id centralised in constants; cached in Chroma.
- **Similarity search:** Chroma vector store (cosine).
- **Advanced RAG:**
  - **Query translation** — multi-query and/or HyDE and/or decomposition.
  - **Structured retrieval** — metadata filters (role, seniority, doc type).
  - **Hybrid search** — vector ⊕ BM25 fused with RRF (Hard target).
  - **Reranker** — cross-encoder or LLM rerank for the top candidates.
- **Grounding & citations:** answers cite retrieved chunks; a grounding check
  flags unsupported claims; "insufficient evidence" is a valid, honest answer.

## 7. Tool architecture

Four Pydantic-typed tools exposed to the LLM via LangChain tool-calling; each
returns structured JSON and its call/result is shown in the UI:

1. **Job Description Analyzer** (`src/tools/job_description.py`) — required
   skills, responsibilities, seniority, themes.
2. **Candidate Gap Analyzer** (`src/tools/gap_analyzer.py`) — background vs role
   → matched strengths and prioritised gaps.
3. **Preparation Plan Calculator** (`src/tools/preparation_plan.py`) — gaps +
   available time → a prioritised, time-boxed plan (deterministic maths, no
   invented numbers).
4. **Interview Question Generator** (`src/tools/interview_questions.py`) —
   role-specific questions (can reuse Interview Practice Studio prompt patterns).

The orchestrator validates tool arguments, bounds tool-call loops, and never
lets a tool fabricate evidence — grounded facts come from retrieval.

## 8. Security architecture

- **Input guard** (`src/security/input_guard.py`) — length/shape validation
  (reuse `src/security.validate_field`).
- **Injection guard** (`src/security/injection_guard.py`) — reuse the deterministic
  weighted injection detector (`src/security.detect_injection`) on the user query
  **and on retrieved documents** (indirect injection defence).
- **Grounding** — retrieved content is treated as untrusted data, never as
  instructions; the system prompt is never exposed.
- **Secrets** — reuse `src/config.py` (secrets→env, no default key, masked
  `SecretStr`); never log/commit keys.
- **Output** — no secret/system-prompt leakage; safe-metadata-only logging.

## 9. Testing strategy

- **Unit:** chunking, cleaners, metadata filters, hybrid fusion, each tool's
  logic, guards. All offline/mocked — **no live API calls in CI** (embeddings/LLM
  are faked/injected, mirroring the existing test approach).
- **Retrieval evaluation** (`src/evaluation/retrieval_eval.py`) — labelled
  query→relevant-doc set; measure recall@k, MRR/nDCG.
- **RAG evaluation** (`src/evaluation/rag_eval.py`) — faithfulness/groundedness,
  citation correctness, answer relevance on a small curated dataset (Hard target).
- **UI smoke** via Streamlit `AppTest`; optional Playwright for browser journeys.

## 10. Phased implementation roadmap

| Phase | Deliverable |
|---|---|
| 0 | Audit + this plan + branch (**current**) |
| 1 | Config, constants, models; OpenRouter + LangChain wiring; usage tracker |
| 2 | Ingestion (loaders, cleaners, chunking, indexer) + `scripts/ingest.py` |
| 3 | Vector retrieval (Chroma) + similarity search + `scripts/inspect_index.py` |
| 4 | Query translation + metadata filters + hybrid (BM25) + reranker |
| 5 | RAG chain: context builder, citations, grounding |
| 6 | Four tools + tool-calling loop + tool-call visibility |
| 7 | Streamlit UI: chat, sources, retrieved context, tool calls, progress, usage |
| 8 | Security: input + injection guards (incl. retrieved-doc injection) |
| 9 | Token/cost tracking surfaced in UI + conversation history/export |
| 10 | Hybrid-search tuning + RAG evaluation harness + `scripts/evaluate_rag.py` |
| 11 | E2E, performance, docs, production readiness |

## 11. Assignment traceability matrix

| Requirement | Where | Status |
|---|---|---|
| RAG (KB, ingestion, chunking, embeddings, similarity) | `src/copilot/ingestion/*`, `src/copilot/embeddings.py`, `src/copilot/vectorstore.py`, `src/copilot/retrieval/vector.py` | Done (Ph 2–3) |
| LangChain | `src/copilot/rag/chain.py`, `src/copilot/llm/openrouter.py`, `src/copilot/tools/*` | Done |
| OpenRouter | `src/copilot/llm/openrouter.py` | Done |
| Query translation | `src/copilot/rag/translation.py` | Done (Ph 4) |
| Structured retrieval | `src/copilot/rag/translation.py` (`sanitize_filters`) | Done (Ph 4) |
| **Core: Tool Calling — 4 tools** | `src/copilot/tools/*` | **Done (Ph 6)** |
| Domain specialisation | career KB + prompts + domain tools | Done |
| **Domain security / injection** | `src/copilot/security/*`, enforced in `service.py` | **PASS (Ph 8)** |
| Error handling / validation | Pydantic models + controlled errors throughout | Done |
| Streamlit UI (sources, tool visibility, progress) | `src/career/ui.py` via unified `app.py` (OS-2) | Done |
| **Opt (M):** prompt-injection protection | `src/copilot/security/*`; 30-case eval | **PASS (Ph 8)** |
| **Opt (M):** token/cost tracking | Career `UsageLedger` (`src/core/usage.py`, tokens by operation; cost honestly "unavailable"); Interview `PricingService` (reported→calculated→none) | **PASS (Ph 9R)** |
| **Opt (M):** conversation history/export | Career history + JSON/CSV + combined session export (`src/copilot/history.py`, `src/integration/export.py`) | **PASS (Ph 9R)** |
| **Opt (H):** hybrid search | `src/copilot/retrieval/{keyword,hybrid,fusion}.py` | **PASS (Ph 5)** |
| **Opt (H):** RAG evaluation | `src/copilot/evaluation/rag_eval.py`, `scripts/eval_rag.py`, `evaluations/*` (33-case dataset; vector/keyword/hybrid + translation + tool-selection + citations) | **PASS (Ph 11R)** |

Targets **all core** requirements, **3 medium** (exceeds 2) and **2 hard**
(exceeds 1).

### Core requirement: Tool Calling

- **Implementation:** LangChain tool calling over the OpenRouter chat model. Tools
  are advertised via `StructuredTool` (`build_langchain_tools`) and bound to the
  model; the model’s `tool_calls` are parsed (`parse_tool_calls`) and dispatched
  through `ToolInvoker`, which validates arguments against each tool’s Pydantic
  schema, times the call, and records a safe `ToolExecution`. It is **not** an
  autonomous agent: only the four registered tools can run — no arbitrary Python,
  shell, filesystem or network.
- **Tools:** Job Description Analyzer (`job_analyzer.py`, LLM), Candidate Gap
  Analyzer (`gap_analyzer.py`, deterministic), Preparation Plan Calculator
  (`prep_planner.py`, deterministic arithmetic), Interview Question Generator
  (`question_generator.py`, LLM). Schemas in `tools/schemas.py`, registry/invoker
  in `tools/registry.py`.
- **Tests:** `tests/test_copilot_tools.py` — job/gap/prep/question calls,
  deterministic match + arithmetic, no-tool case, sequential tools, malformed
  args, tool exception, unsupported tool, LangChain tool-call parsing, and
  no-arbitrary-execution.
- **Demonstration path:** app **Career Tools** page — paste a job description →
  Analyze → Gap Analyzer → Preparation Plan → Question Generator, with a
  collapsed **Tools used** panel of safe execution records.
- **Docs:** [`docs/tool_calling.md`](tool_calling.md).

## 12. Reuse from the existing codebase

Directly reusable (proven + tested on `main`): `src/openrouter_client.py`,
`src/config.py` (secrets), `src/security.py` (injection guard + validation),
`src/pricing_service.py` (usage/cost), `src/response_parser.py` (safe JSON),
`src/models.py` patterns, and the Streamlit UI/testing conventions. New RAG,
retrieval, ingestion, tools and evaluation modules are additive.

## 13. Risks

- **Knowledge-base quality/licensing** — curate reputable, redistributable
  sources; track provenance.
- **New heavy dependencies** (LangChain, Chroma) — introduce incrementally
  (Phase 1+), keep CI offline via fakes.
- **Retrieved-document prompt injection** — guard retrieved text, not just user
  input.
- **Cost/latency of embeddings + rerank** — cache embeddings; bound top-k;
  measure with a confirmation-gated live suite.
- **Scope** — five optional targets is ambitious; the roadmap sequences them so
  core lands first.

## 14. Next phase

**Phase 1** — establish config/constants/models, wire OpenRouter through
LangChain, and stand up the usage tracker, without ingesting documents yet.
