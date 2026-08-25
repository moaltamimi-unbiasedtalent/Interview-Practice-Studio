# Interview OS Coach — Migration Plan (OS-1)

Evidence-based plan produced during the OS-1 audit. **No code moved in OS-1.**

## Starting point

- **Repository:** single monorepo at
  `/Volumes/Abu Aaliyah/Claude Projects/Interview Practice Studio/Interview-Practice-Studio`
  (remote `moaltamimi-unbiasedtalent/Interview-Practice-Studio`).
- **Both products already live here** — Interview Practice (`app.py` + `src/*.py`)
  and Career Intelligence (`copilot_app.py` + `src/copilot/*`). There is **no
  separate Interview Practice Studio repo to import.**
- **Integration branch:** `feature/interview-os-integration`, created from
  `0157684` (Phase 8 tip == `main`). `main` untouched.
- **Test baseline:** 846 passed, 1 skipped (Career 155 / Interview 691 +1 skip).
- **Python:** 3.11.15 (`requires-python >=3.10`).

## Target repository / structure

See `docs/interview_os_architecture.md`. Modular monolith: `src/core`,
`src/career`, `src/interview`, `src/integration`, `src/ui`; one `app.py`; one
`streamlit run app.py`.

## 1) Dependency compatibility audit

There is **one** `pyproject.toml` already serving both products, so there are no
two dependency sets to reconcile — the risky part is already done. Installed
versions (this venv):

| Package | pyproject spec | Installed | Used by | Classification |
| --- | --- | --- | --- | --- |
| Python | `>=3.10` | 3.11.15 | both | compatible |
| streamlit | `>=1.40,<2.0` | 1.61.1 | both | compatible |
| httpx | `>=0.27,<1.0` | 0.28.1 | interview (OpenRouter client) | compatible |
| pydantic | `>=2.9,<3.0` | 2.13.4 | both | compatible |
| python-dotenv | `>=1.0,<2.0` | 1.2.2 | both | compatible |
| pandas | `>=2.2,<3.0` | 2.3.3 | both (CSV, tables) | compatible |
| openpyxl | `>=3.1,<4.0` | 3.1.5 | interview (Excel export) | compatible |
| sqlalchemy | `>=2.0,<3.0` | 2.0.52 | interview (persistence) | compatible |
| langchain | `>=0.3,<0.4` | 0.3.30 | career | compatible |
| langchain-openai | `>=0.2,<0.4` | 0.3.35 | career | compatible |
| pypdf | `>=4.0,<6.0` | 5.9.0 | career (ingestion) | compatible |
| langchain-community | `[rag]` `>=0.3,<0.4` | not installed | (listed only) | **obsolete/optional** — our vector store uses `chromadb` directly; not imported anywhere. Candidate for removal. |
| chromadb | `[rag]` `>=0.5,<1.0` | 0.6.3 | career (vector store) | optional (extra) |
| rank-bm25 | `[rag]` `>=0.2,<1.0` | 0.2.2 | career (BM25) | optional (extra) |
| google-cloud-speech | `[speech]` `>=2.26,<3.0` | 2.40.0 | interview (STT) | optional (extra) |
| google-genai | `[live]` `>=0.8,<2.0` | 1.75.0 | interview (Gemini Live) | optional (extra) |
| alembic / psycopg | `[db]` | — | interview (prod DB) | optional (extra) |
| @google/genai (npm) | frontend | ^2.17.1 | live component | optional (Node) |
| @mediapipe/tasks-vision | frontend | ^0.10.0 | live component | optional (Node) |
| streamlit-component-lib | frontend | ^2.0.0 | live component | optional (Node) |
| @playwright/test | `e2e/` | ^1.48.0 | e2e (local) | optional (Node) |

**Conflicts:** none requiring version reconciliation. **Do not blanket-upgrade.**
Only action item: consider dropping the unused `langchain-community` from `[rag]`
(verify with a grep for imports first) in a later phase — not now.

## 2) Naming-collision audit

Duplicate module names across the two halves (ambiguous once both sit under
`src/`):

| Name | Interview (now) | Career (now) | Target interview | Target career |
| --- | --- | --- | --- | --- |
| `config.py` | `src/config.py` (`AppConfig`) | `src/copilot/config.py` (`CopilotConfig`) | `src/interview/config.py` | `src/career/config.py` |
| `models.py` | `src/models.py` | `src/copilot/models.py` | `src/interview/models.py` | `src/career/models.py` |
| `constants.py` | `src/constants.py` | `src/copilot/constants.py` | `src/interview/constants.py` | `src/career/constants.py` |
| `security` | `src/security.py` (module) | `src/copilot/security/` (package) | `src/interview/security.py` | `src/career/security/` |
| `ui_helpers.py` | `src/ui_helpers.py` | inline in `copilot_app.py` | `src/interview/ui/helpers.py` + shared bits to `src/ui/` | `src/career/ui/` |
| OpenRouter | `src/openrouter_client.py` (HTTPX) | `src/copilot/llm/openrouter.py` (LangChain) | `src/interview/openrouter_client.py` | `src/career/llm/openrouter.py` |

Collisions are resolved by **package namespacing** (each under its product
package). No shared top-level `config`/`models`/`constants`; genuinely shared
values move to `src/core/*`. No ambiguous imports permitted post-migration.

## 3) Migration sequence (proposed; each its own phase, each fully gated)

1. **Scaffolding** — create `src/core`, `src/career`, `src/interview`,
   `src/integration`, `src/ui` packages (empty `__init__`), no moves yet.
2. **Career move** — relocate `src/copilot/*` → `src/career/*` (mechanical
   rename); update imports + tests; keep `copilot_app.py` working temporarily.
   Career is self-contained → lowest risk, do first.
3. **Core extraction** — pull shared infra (logging, errors, usage/cost model,
   shared secret reader) into `src/core`; both products import from it.
4. **Interview move** — relocate `src/*.py` → `src/interview/*` (services,
   prompts, speech, live, timing, security, persistence); update imports + tests;
   keep `components/live_interviewer/` path stable.
5. **Integration contract** — implement `PreparationContext`, `preparation_context`
   builder, `handoff` ("Practise this role").
6. **UI unification** — build `src/ui/navigation.py` + `home.py`; fold
   `copilot_app.py` pages into `src/career/ui/` and `app.py` renderers into
   `src/interview/ui/`; single `app.py` dispatches. Retire `copilot_app.py`.
7. **Cleanup** — remove dead entry points, tidy `[rag]` extra, refresh README +
   traceability.

Order rationale: move the self-contained career package first (cheap, isolated),
extract core, then the larger interview surface, then wire the contract, then UI.

## 4) Conflict list

- Duplicate module names (above) — resolved by namespacing.
- Two entry points → must converge to one `app.py` (phase 6).
- Two config models — intentionally kept separate; only secret-reading shared.
- Two OpenRouter integrations — intentionally kept (rule 3).
- Two security implementations — kept separate now; possible `core/security`
  primitive extraction later, without deleting either.
- `components/live_interviewer/` frontend path referenced by `src/live_interview.py`
  — keep the path stable during the interview move (or update the reference).

## 5) Test strategy

- Full suite (`pytest`) is the safety net after **every** step; never drop tests
  for import-path churn (rule 10) — update imports instead.
- Move files and their tests together; run the moved subset first, then full.
- Keep both smoke tests green (`test_app_smoke.py`, `test_copilot_app_smoke.py`)
  until the unified `app.py` replaces them with one smoke test.
- Add an `integration` test for `PreparationContext` round-trip when it lands.

## 6) Rollback approach

- All work on `feature/interview-os-integration`; `main` stays at `0157684`.
- Each phase is one (or few) commits; revert a phase with `git revert`/reset on
  the branch. Physical moves use `git mv` so history is preserved and reversible.
- Because each phase leaves the suite green, any regression is caught before the
  next phase, keeping rollback local to the last phase.

## 7) Module boundaries (enforced)

`career` and `interview` never import each other; cross-module data flows only
through `src/integration` (plain Pydantic) or `src/core` (infra). `app.py`/`src/ui`
import product **UI** entry points only. See architecture doc.

## 8) Sprint-requirement preservation

Tracked in `docs/sprint_requirements_after_integration.md` — every Advanced RAG,
Tool Calling, LangChain, domain and security requirement is mapped to its future
location with its tests. Integration must not remove or obscure sprint work.
