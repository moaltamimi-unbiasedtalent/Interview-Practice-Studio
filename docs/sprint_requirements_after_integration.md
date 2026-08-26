# Sprint Requirements — Preservation After Integration

Proves that folding Career Intelligence into Interview OS Coach does **not**
remove or obscure the Turing sprint work. Each requirement maps from its current
location to its future unified location. Nothing is deleted; paths change only
when files physically move (tests move with them).

Legend: **Now** = current path (Phase 8). **After** = target under the modular
monolith. **Tests** = covering tests.

## Advanced RAG

| Requirement | Now | After | Tests |
| --- | --- | --- | --- |
| Knowledge base / ingestion | `src/copilot/ingestion/*`, `scripts/ingest.py` | `src/career/ingestion/*` | `test_copilot_ingestion.py` |
| Chunking + dedup | `src/copilot/ingestion/chunking.py` | `src/career/ingestion/chunking.py` | `test_copilot_ingestion.py` |
| Embeddings | `src/copilot/embeddings.py` | `src/career/embeddings.py` | `test_copilot_rag.py` |
| Vector retrieval (Chroma) | `src/copilot/vectorstore.py`, `retrieval/vector.py` | `src/career/vectorstore.py`, `retrieval/vector.py` | `test_copilot_rag.py` |
| Query translation | `src/copilot/rag/translation.py` | `src/career/rag/translation.py` | `test_copilot_translation.py` |
| Structured (metadata) retrieval | `translation.sanitize_filters` + store filters; **multi-source structured lanes** (`src/copilot/knowledge/*`: role + compensation DBs, router) | same under `career` | `test_copilot_translation.py`, `test_copilot_rag.py`, `test_copilot_knowledge.py` |
| Domain knowledge base + routing | `src/copilot/knowledge/` (roles/skills/compensation, provenance, authority, deterministic router) | `src/career/knowledge/` | `test_copilot_knowledge.py` |
| Hybrid search (BM25 + vector) | `src/copilot/retrieval/{keyword,hybrid,fusion}.py` | `src/career/retrieval/*` | `test_copilot_hybrid.py` |
| RAG evaluation | `src/copilot/evaluation/*`, `scripts/eval_retrieval.py` | `src/career/evaluation/*` | (eval harness) |

## Tool calling (4 tools)

| Requirement | Now | After | Tests |
| --- | --- | --- | --- |
| Job Description Analyzer | `src/copilot/tools/job_analyzer.py` | `src/career/tools/job_analyzer.py` | `test_copilot_tools.py` |
| Candidate Gap Analyzer | `src/copilot/tools/gap_analyzer.py` | `src/career/tools/gap_analyzer.py` | `test_copilot_tools.py` |
| Preparation Plan Calculator | `src/copilot/tools/prep_planner.py` | `src/career/tools/prep_planner.py` | `test_copilot_tools.py` |
| Interview Question Generator | `src/copilot/tools/question_generator.py` | `src/career/tools/question_generator.py` | `test_copilot_tools.py` |
| LangChain tool-calling glue | `src/copilot/tools/registry.py` | `src/career/tools/registry.py` | `test_copilot_tools.py` |

## LangChain / orchestration

| Requirement | Now | After | Tests |
| --- | --- | --- | --- |
| LangChain over OpenRouter | `src/copilot/llm/openrouter.py` | `src/career/llm/openrouter.py` | `test_copilot_llm.py` |
| RAG + tools orchestration | `src/copilot/service.py`, `rag/*` | `src/career/service.py`, `rag/*` | `test_copilot_orchestration.py` |

## Domain specialisation

| Requirement | Now | After | Tests |
| --- | --- | --- | --- |
| Career-intelligence domain | `src/copilot/*` (KB, prompts, tools) | `src/career/*` | career suite |

## Security

| Requirement | Now | After | Tests |
| --- | --- | --- | --- |
| Prompt-injection protection (medium optional) | `src/copilot/security/*` | `src/career/security/*` | `test_copilot_security.py` |
| Injection eval artifact | `data/eval/injection_cases.json`, `security_results.json` | unchanged (data/) | `test_copilot_security.py` |
| Interview security guard | `src/security.py` | `src/interview/security.py` | `test_security.py`, `test_security_hardening.py` |

## Streamlit / UX requirements

| Requirement | Now | After | Tests |
| --- | --- | --- | --- |
| Streamlit app | `copilot_app.py` (career), `app.py` (interview) | one `app.py` + `src/*/ui/` | `test_copilot_app_smoke.py`, `test_app_smoke.py` |
| Sources / citations shown | `copilot_app.py` Chat + RAG Inspector | `src/career/ui/` | `test_copilot_rag.py` |
| Tool-call visibility | RAG Inspector + "Tools used" | `src/career/ui/` | `test_copilot_tools.py` |
| Progress states | Chat status stages | `src/career/ui/` | app smoke |

## Optional tasks status

| Optional task | Tier | Status | Now |
| --- | --- | --- | --- |
| Prompt-injection protection | medium | PASS | `src/copilot/security/*` |
| Token/cost tracking | medium | PASS | Career `src/core/usage.py` (tokens by operation; cost "unavailable"), Interview `src/pricing_service.py` (reported→calculated→none) |
| Conversation history/export | medium | PASS | `src/copilot/history.py` (JSON/CSV), `src/integration/export.py` (combined) |
| Hybrid search | hard | PASS | `src/copilot/retrieval/*` |
| RAG evaluation | hard | PASS | 11R baseline (preserved in `evaluations/baseline/`): `rag_eval.py`, `scripts/eval_rag.py`. 11R-A measured the expanded lanes: `expanded_eval.py`, `scripts/eval_expanded.py`, `evaluations/expanded_architecture_*` (routing 1.0, structured-role hit/provenance 1.0, compensation 1.0 on samples; core retrieval Δ=0 vs baseline) |

## Guarantee

- Career Intelligence remains a **single cohesive package** (`src/career/`) with
  its own tests, so it stays independently reviewable for the sprint.
- No sprint capability is removed by integration; only import paths change, and
  only when files move — with their tests. Any move that would drop coverage is
  out of scope (global rule 10).
