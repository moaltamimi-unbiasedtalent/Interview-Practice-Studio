# Career Intelligence — Quality Optimisation Audit (Phase OPT)

Audit of the current implementation **before** any OPT coding, so completed
functionality is not reimplemented. Statuses: **DONE** (already implemented),
**PARTIAL**, **TODO** (not implemented), **N/R** (not recommended without evidence).

| # | Requirement | Current implementation | Status | Evidence | Recommended change | Risk | Measurement |
|---|---|---|---|---|---|---|---|
| 1A | Embedding provider `auto` + graceful no-key start | `DEFAULT_EMBEDDING_PROVIDER="auto"`; `build_embedder` falls back to local hash | DONE | `constants.py:67`, `embeddings.py` | keep | low | app starts w/o key |
| 1A | `auto` uses dedicated embedding key only (not chat key) | fixed in CI-PH1 — `auto` requires `embedding_api_key` | DONE | `embeddings.py build_embedder` | keep; document | low | test_core |
| 1A | Default semantic model configurable | `text-embedding-3-small`, `COPILOT_EMBEDDING_MODEL/BASE_URL/API_KEY` | DONE | `constants.py:63-64`, `config.py:23-26` | keep | low | — |
| 1A | Non-secret embedding status + UI warning when local | eval page mentions offline; **no chat-side quality-mode status/warning** | PARTIAL | `career/ui.py` | add `embedding_status()` + UI warning | low | UI smoke |
| 1B | Reranker interface (`BaseReranker`, NoOp + one real) + trace | none | TODO | no rerank config | add interface, NoOp default, optional LLMReranker behind config | med | rerank trace + eval |
| 1C | Section-aware chunking strategy | recursive baseline only; no `COPILOT_CHUNKING_STRATEGY` | PARTIAL | `ingestion/chunking.py`, `constants CHUNK_*` | add `baseline|section` strategy, keep default | med | v2 eval |
| 1D | Real-corpus retrieval eval (v2, configs) | 11R/11R-A exist; no v2 matrix | TODO | `evaluations/` | add `evaluations/retrieval_quality_v2/` harness | low | new run |
| 2 | Hybrid weights configurable | `COPILOT_HYBRID_VECTOR_WEIGHT/KEYWORD_WEIGHT`, RRF weighted | DONE | `config.py:30-31,55-56`, `fusion.py` | keep | low | — |
| 2 | Weight validation (≥0, not both 0) | none | PARTIAL | `config.py` | add validation/fallback | low | unit test |
| 2A | Adaptive weighting (experimental, default off) | none | TODO | — | add `COPILOT_HYBRID_ADAPTIVE=false` + deterministic reason codes | med | eval; off by default |
| 2B | Inspector: channels/RRF/effective weights/dominant signal | channels + fused shown; no effective weights / dominant-signal label | PARTIAL | `career/ui.py` RAG Inspector | add effective weights + deterministic dominant-signal | low | UI smoke |
| 3A | Invalid citation markers removed from answer | output guard **detects** invalid markers but does **not strip** them | PARTIAL | `security/output_guard.py` | sanitise invalid `[n]` from `safe_answer` | low | unit tests |
| 3B | Evidence vs general-guidance UI separation | synthesis prompt asks for sections; UI renders answer as-is | PARTIAL | `rag/synthesis.py`, `career/ui.py` | light section renderer w/ graceful fallback | low | UI smoke |
| 3C | Structured fact display (currency/period/year/geo) | present in evidence text + metadata; not a dedicated visible panel | PARTIAL | `models.KnowledgeEvidence`, `career/ui.py` | render a compact structured-facts panel | low | UI smoke |
| 3D | Deterministic faithfulness checks (v2) | product_coverage has citation/provenance; no dedicated faithfulness_v2 | PARTIAL | `evaluations/product_coverage` | add `evaluations/faithfulness_v2/` | low | new run |
| 4A | Session TTL cache (translation/resolution) | none | TODO | — | bounded TTL cache, session-scoped, non-sensitive keys | med | cache-hit metric |
| 4B | Exact normalised-question cache; no semantic query-cache | none | TODO | — | exact-key only (per 4B) | low | test |
| 4C | Quality/Balanced/Cheap mode | none | TODO | — | add mode → model/top_k/alt-queries/rerank | med | trace |
| 4D | UsageLedger + "Cost unavailable" | `UsageLedger`; honest "Cost unavailable" | DONE | `core/usage.py`, `history.py:173` | keep | low | — |
| 5A | Guided tool sequence (no agent loops) | fixed registry + guided Career Tools | DONE | `tools/*`, `career/ui.py` | keep | low | — |
| 5B | Safe tool summaries rendered | `_render_tool_executions` shows name/status/summary/duration | DONE | `career/ui.py` | keep; minor polish | low | — |
| 5C | Dry-run "preview what it will do" | none | TODO | — | deterministic plan from router + intent rules | low | test |
| 5D | Journey progress indicator | `WORKFLOW_STEPS` static breadcrumb only | PARTIAL | `ui/navigation.py:45` | compact per-module progress | low | UI smoke |
| 5E | Practise-this-role provenance labels | handoff editable; no field provenance labels | PARTIAL | `career/ui.py`, `integration/*` | add short provenance captions | low | UI smoke |
| 5F | Demo knowledge pack loader | fixtures exist; no `load_sample_knowledge.py`, no demo store | TODO | `scripts/` | add offline demo loader (separate store, --force) | med | run offline |
| 6A | Distribution name `interview-os-coach` | `interview-practice-studio` | TODO | `pyproject.toml:2` | rename dist (keep import pkgs) | low | editable install |
| 6B | copilot(domain)/career(UI) canonical, no "temporary" language | some docs implied `src/career` would replace `src/copilot` | PARTIAL | `docs/sprint_requirements_after_integration.md` | document canonical split | low | — |
| 6C | Product labels (Interview OS Coach / Career Intelligence) | present in UI | DONE | `ui/*`, `constants` | keep | low | — |
| 6D | Reviewer mode (Career-only) | none | TODO | — | `COPILOT_REVIEWER_MODE` nav filter | low | UI smoke |
| 7 | Held-out relevance + faithfulness eval (v2) | lexical probes + product_coverage | PARTIAL | `evaluations/` | add `evaluations/quality_v2/` (labelled set, checks, human template, LLM-judge optional) | low | new run |
| 8A | Answer freshness (year/version/refreshed) | evidence carries year; not surfaced as a freshness line | PARTIAL | `models`, `career/ui.py` | surface freshness on comp/labour answers | low | UI smoke |
| 8B | Status CURRENT/REFRESH DUE/UNKNOWN computed | field exists, effectively always UNKNOWN | PARTIAL | `knowledge/status.py:50` | compute from refresh policy + last acquisition | low | status run |
| 8C | Freshness/refresh helper scripts | none | TODO | `scripts/` | `check_source_freshness.py` (+ dry-run refresh) | low | run offline |

## Key verifications (as the prompt requested)
- **Semantic embedding support already exists** (OpenAI-compatible via `OpenAIEmbedder`); local-hash is the lexical fallback — confirmed. ✔
- **Hybrid weights already configurable** (`COPILOT_HYBRID_*`, weighted RRF) — confirmed; only validation + adaptive are new. ✔
- **Product-workflow terms already in navigation** (`WORKFLOW_STEPS`) — confirmed; only the visual progress is new. ✔
- **Tool safe summaries already rendered** — confirmed. ✔
- **Distribution name is still `interview-practice-studio`** — confirmed; rename in OPT-6A. ✔
- **UsageLedger + honest "Cost unavailable"** already present — confirmed. ✔

## Scope decision
Skip DONE items. Implement PARTIAL/TODO in small commits, prioritising low-risk,
high-value, offline-measurable work; defaults stay unchanged unless a real
measurement justifies a change. Historical 11R/11R-A/KB-2/product-coverage
artifacts are never overwritten; new work lands under new `*_v2` directories.
