# Interview OS Coach — Capability Matrix (OS-1 audit)

**Audit only — no code moved.** Integration branch `feature/interview-os-integration`
from commit `0157684` (Phase 8 tip = `main`).

## Important finding: this is already one repository

The "primary" (Career Intelligence) repo and the Interview Practice Studio source
are the **same repository at the same path**
(`/Volumes/Abu Aaliyah/Claude Projects/Interview Practice Studio/Interview-Practice-Studio`).
Career Intelligence was built as the repo's evolution, so both products already
coexist as a monorepo:

- **Interview Practice Studio** — entry point `app.py` (1852 lines) + flat modules
  under `src/*.py`.
- **Career Intelligence** — entry point `copilot_app.py` (586 lines) + package
  `src/copilot/*`.
- **One** `pyproject.toml`, one venv, one test suite (`tests/`), one
  `components/live_interviewer/` frontend.

Consequences: there is no external repo to clone; "migration" is an in-repo
refactor into `src/core|career|interview|integration|ui`, and the second entry
point (`copilot_app.py`) must fold into a single `app.py`. This lowers dependency
risk (already reconciled in one pyproject) and raises naming-collision risk
(duplicate `config/models/constants/security`).

Test baseline: **846 passed, 1 skipped** — Career subset **155 passed**,
Interview Practice **691 (+1 skipped)**.

---

## 1. Shared-infrastructure candidates → `src/core/`

| Capability | Interview Practice | Career Intelligence | Note |
| --- | --- | --- | --- |
| Configuration / secrets | `src/config.py` (`AppConfig`, `load_config`, auth/db/secrets) | `src/copilot/config.py` (`CopilotConfig`) | **Two config models.** Keep both; extract a shared secret-reading pattern into `core`. Do NOT merge into one god-config. |
| Constants | `src/constants.py` | `src/copilot/constants.py` | Keep module-scoped; only truly shared values (app name, currency) go to `core`. |
| OpenRouter access | `src/openrouter_client.py` (HTTPX client, `OpenRouterError`) | `src/copilot/llm/openrouter.py` (LangChain `ChatOpenAI` factory) | **Two intentional clients** (rule 3). Both may share credentials from `core`, not implementation. |
| Usage / cost | `src/pricing_service.py`, usage in sidebar | `UsageRecord` model + RAG Inspector | Cost model is a `core` candidate; keep pricing service as interview logic. |
| Safe logging | ad hoc | `src/copilot/logging_utils.py` | Promote a `core/logging.py`. |
| Generic errors | `OpenRouterError`, `ServiceError` | `CopilotConfigError`, `RagChainError`, `ToolError` | Introduce `core/errors.py` base classes; keep specifics local. |
| Security primitives | `src/security.py` (interview injection/validation) | `src/copilot/security/*` (scanner, guards) | Overlapping intent, different code. Reconcile carefully in a later phase; do not delete either now. |
| Session utilities | `src/session_manager.py`, `src/persistence.py`, `src/repository.py` | Streamlit `session_state` only | Interview-owned; expose read-only handoff via `integration`. |
| UI helpers | `src/ui_helpers.py` | inline in `copilot_app.py` | Promote shared bits to `src/ui/`. |

## 2. Career-only → `src/career/`

| Capability | Location |
| --- | --- |
| Knowledge-base ingestion (PDF/TXT/MD/CSV, chunking, dedup) | `src/copilot/ingestion/*`, `scripts/ingest.py` |
| Embeddings abstraction (OpenAI + local) | `src/copilot/embeddings.py` |
| Chroma vector store (+ in-memory fallback) | `src/copilot/vectorstore.py`, `scripts/build_index.py` |
| Vector retrieval | `src/copilot/retrieval/vector.py` |
| BM25 keyword retrieval | `src/copilot/retrieval/keyword.py` |
| Hybrid retrieval + RRF fusion | `src/copilot/retrieval/hybrid.py`, `fusion.py`, `factory.py` |
| Advanced query translation (intent, multi-query, filters) | `src/copilot/rag/translation.py`, `routing.py` |
| RAG orchestration (context, citations, synthesis, chain) | `src/copilot/rag/*`, `src/copilot/service.py` |
| Career tools (4) | `src/copilot/tools/*` |
| RAG/retrieval + security evaluation | `src/copilot/evaluation/*`, `scripts/eval_*.py` |
| Career security (injection/guards) | `src/copilot/security/*` |
| Career UI | `copilot_app.py` → `src/career/ui/` |

## 3. Interview-only → `src/interview/`

| Capability | Location | Must survive |
| --- | --- | --- |
| Interview strategy + question flow | `src/interview_service.py` | ✅ |
| Answer evaluation (structured JSON) | `src/evaluation_service.py`, `src/structured_output.py`, `src/response_parser.py` | ✅ |
| Prompt techniques / registry | `src/prompt_registry.py`, `src/prompts.py` | ✅ |
| Final report | `src/report_service.py` | ✅ |
| Session / persistence / repository | `src/session_manager.py`, `src/persistence.py`, `src/repository.py` (SQLAlchemy) | ✅ |
| Auth + health | `src/auth.py`, `src/health.py` | ✅ |
| Pricing / usage | `src/pricing_service.py` | ✅ |
| Voice recording + STT | `src/speech_service.py` (`[speech]`, google-cloud-speech) | ✅ |
| Gemini Live | `src/live_interview.py` + `components/live_interviewer/` (frontend, `@google/genai`) | ✅ |
| Delivery / pacing coach | `src/timing.py`, `src/visual_coach.py`, `src/avatar.py` | ✅ |
| OpenRouter (direct HTTPX) | `src/openrouter_client.py` | ✅ (rule 3) |
| Interview security | `src/security.py` | ✅ |
| Prompt-comparison / jailbreak experiments | `render_prompt_lab` in `app.py`, `tests/test_jailbreak_runner.py`, `test_prompt_comparison.py` | ✅ |

## 4. Integration-specific → `src/integration/`

| Capability | Status | Target |
| --- | --- | --- |
| `PreparationContext` (career → interview handoff contract) | **new** | `src/integration/models.py` |
| "Practise this role" hand-off | **new** | `src/integration/handoff.py` |
| Shared role/job/candidate context | **new** | `src/integration/preparation_context.py` |
| Cross-module navigation (one app, both products) | **new** | `src/ui/navigation.py`, `app.py` |
| Unified home page | **new** | `src/ui/home.py` |

See `docs/interview_os_architecture.md` for the target tree and the
`PreparationContext` contract, and `docs/interview_os_migration_plan.md` for
sequencing.
