# Assignment Traceability — Building Applications with AI

The sprint deliverable is the **Career Intelligence** module. Every requirement
maps to its implementation, files, tests and a demo step. Status reflects what is
actually implemented and tested.

| Requirement | Implementation | Files | Tests | Demo | Status |
| --- | --- | --- | --- | --- | --- |
| **LangChain** | ChatOpenAI over OpenRouter; tool calling; structured output | `src/copilot/llm/openrouter.py`, `src/copilot/tools/*`, `src/copilot/rag/*` | `test_copilot_llm.py`, `test_copilot_tools.py` | Ask a question → RAG Inspector | PASS |
| **OpenRouter** | OpenAI-compatible client (LangChain) + credentials in core config | `src/copilot/llm/openrouter.py`, `src/core/config.py` | `test_copilot_llm.py`, `test_core.py` | Sidebar shows model configured | PASS |
| **Advanced RAG — knowledge base & chunking** | ingestion (PDF/TXT/MD/CSV), cleaning, chunking, dedup | `src/copilot/ingestion/*` | `test_copilot_ingestion.py` | Knowledge Base page | PASS |
| **Embeddings** | pluggable (OpenAI / local), dimensions | `src/copilot/embeddings.py` | `test_copilot_rag.py` | RAG Inspector metrics | PASS |
| **Vector retrieval** | Chroma (persistent) + in-memory fallback | `src/copilot/vectorstore.py`, `retrieval/vector.py` | `test_copilot_rag.py` | RAG Inspector vector hits | PASS |
| **Query translation** | intent, rewrite, multi-query, safe filters | `src/copilot/rag/translation.py` | `test_copilot_translation.py` | RAG Inspector translation | PASS |
| **Structured retrieval** | metadata filters + five structured stores (role/competency/compensation/labour-market) + router with geo precedence | `src/copilot/rag/translation.py`, `src/copilot/knowledge/*` (`structured_ext.py`, `status.py`, `normalisers_ext.py`) | `test_copilot_translation.py`, `test_copilot_knowledge.py`, `test_knowledge_expansion.py` | Role/competency/compensation/shortage query | PASS |
| **Hybrid search (hard optional)** | vector + BM25 fused with RRF | `src/copilot/retrieval/{keyword,hybrid,fusion}.py` | `test_copilot_hybrid.py` | RAG Inspector fused ranking | PASS |
| **Tool calling (≥3 → 4)** | Job Analyzer, Gap Analyzer, Prep Plan, Question Generator | `src/copilot/tools/*` | `test_copilot_tools.py` | Career Tools page | PASS |
| **RAG + tools orchestration** | one non-autonomous service | `src/copilot/service.py` | `test_copilot_orchestration.py` | Chat answer | PASS |
| **Domain specialisation** | careers/roles/skills/competencies/compensation/labour-market across 25 authoritative sources + prompts | `src/copilot/*`, `src/copilot/knowledge/*`, `data/source_manifest.json` | `test_copilot_knowledge.py`, `test_knowledge_expansion.py` | Any career query; Knowledge Base page | PASS |
| **Domain security / prompt injection (medium optional)** | scanner, RAG guard, output guard, safe tool records | `src/copilot/security/*` | `test_copilot_security.py` | Try "ignore instructions…" | PASS |
| **Streamlit UI** | one app, grouped nav, design system | `app.py`, `src/ui/*`, `src/career/ui.py` | `test_os_shell` / `test_copilot_app_smoke.py` | Whole app | PASS |
| **Sources / citations** | numbered context → citations mapping | `src/copilot/rag/context.py` | `test_copilot_rag.py` | Answer "Sources" | PASS |
| **Tool-call visibility** | "Tools used" panel + RAG Inspector | `src/career/ui.py` | `test_copilot_tools.py` | Career Tools / Inspector | PASS |
| **Progress states** | service progress callback | `src/copilot/service.py`, `src/career/ui.py` | `test_service_progress.py` | Ask a question | PASS |
| **Token/cost tracking (medium optional)** | Career usage ledger; Interview PricingService (cost honest) | `src/core/usage.py`, `src/copilot/history.py`, `src/pricing_service.py` | `test_core.py`, `test_career_history.py` | Usage & diagnostics | PASS |
| **Conversation history/export (medium optional)** | history + JSON/CSV + combined export | `src/copilot/history.py`, `src/integration/export.py` | `test_career_history.py` | Usage & diagnostics | PASS |
| **RAG evaluation (hard optional)** | 11R baseline + 11R-A expanded | `src/copilot/evaluation/*`, `scripts/eval_rag.py`, `scripts/eval_expanded.py`, `evaluations/*` | `test_rag_eval.py`, `test_expanded_eval.py` | Evaluation page | PASS |

**Optional-task tally:** 3 medium (injection protection, token/cost, history/export)
+ 2 hard (hybrid search, RAG evaluation) — exceeds the sprint minimums.

See also [docs/sprint_requirements_after_integration.md](sprint_requirements_after_integration.md)
for the pre/post-integration location map.
