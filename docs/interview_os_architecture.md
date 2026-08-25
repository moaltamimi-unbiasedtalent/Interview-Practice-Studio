# Interview OS Coach — Target Architecture (OS-1 design)

Design target, **not** an instruction to move files now. Modular monolith, one
Streamlit app, one URL. Module boundaries are enforced: cross-module talk goes
through `src/integration/`, never arbitrary imports.

## Target tree

```
Interview OS Coach
│
├── app.py                      # thin: nav + page dispatch only (no business logic)
│
├── src/
│   ├── core/                   # shared infra (no product logic)
│   │   ├── config.py           # shared secret-reading; per-product configs stay separate
│   │   ├── errors.py
│   │   ├── logging.py
│   │   ├── usage.py            # UsageRecord / cost model
│   │   └── security/           # generic primitives shared by both guards
│   │
│   ├── career/                 # = today's src/copilot/*  (Career Intelligence)
│   │   ├── config.py  constants.py  models.py
│   │   ├── embeddings.py  vectorstore.py  service.py
│   │   ├── ingestion/  retrieval/  rag/  tools/  evaluation/  security/
│   │   ├── llm/                # openrouter (LangChain ChatOpenAI factory)
│   │   └── ui/                 # = today's copilot_app.py pages
│   │
│   ├── interview/              # = today's src/*.py (Interview Practice)
│   │   ├── config.py  constants.py  models.py
│   │   ├── services/           # interview, evaluation, report, session, repository, pricing
│   │   ├── prompts/            # prompt_registry, prompts, structured_output, response_parser
│   │   ├── speech/             # speech_service
│   │   ├── live/               # live_interview (+ components/live_interviewer)
│   │   ├── timing/             # timing, visual_coach, avatar (delivery/pacing)
│   │   ├── security.py  openrouter_client.py  auth.py  health.py  persistence.py
│   │   └── ui/                 # = today's app.py page renderers
│   │
│   ├── integration/            # the only cross-module surface
│   │   ├── models.py           # PreparationContext (contract)
│   │   ├── preparation_context.py  # build from career outputs
│   │   └── handoff.py          # "Practise this role" career → interview
│   │
│   └── ui/
│       ├── navigation.py       # top-level nav across both products
│       ├── home.py             # unified landing
│       ├── shared.py           # shared widgets
│       └── styles.py
│
├── components/live_interviewer/   # unchanged Streamlit component (Gemini Live)
├── data/                          # raw / processed / chroma / eval (ignored where intended)
├── evaluations/                   # exported experiment artifacts
├── tests/                         # unchanged suite (import paths updated only when files move)
└── docs/
```

### Boundary rules

- `career` and `interview` **must not import each other**. Any shared data
  crosses via `integration` (plain Pydantic) or `core` (infra).
- `app.py` and `src/ui/*` import product *UI* entry points only, never product
  service internals.
- Rule 3 preserved: two OpenRouter paths remain — `interview/openrouter_client.py`
  (HTTPX) and `career/llm/openrouter.py` (LangChain). They may share credentials
  from `core.config`, not implementations.

## Entry-point unification

Today: `streamlit run app.py` (Interview) and `streamlit run copilot_app.py`
(Career) are separate. Target: a single `app.py` whose top-level nav routes to
either product's pages (career pages call `career.ui`, interview pages call
`interview.ui`). `copilot_app.py` is retired once its pages live under
`career/ui/` and are reachable from the unified nav.

## PreparationContext contract (design)

The **only** data structure that crosses career → interview. Plain domain data:
no Chroma objects, no LangChain documents, no retriever internals, no
OpenRouter-specific objects. Produced by Career Intelligence, consumed by
Interview Practice.

```python
# src/integration/models.py  (design — implemented in a later phase)
class SourceReference(BaseModel):
    title: str | None
    source: str | None
    page: int | None

class PreparationContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Role framing
    target_role: str
    industry: str | None = None
    company_context: str | None = None
    job_description: str | None = None          # sanitised text only
    seniority: str | None = None

    # Requirements (from Job Description Analyzer)
    required_skills: list[str] = []
    key_responsibilities: list[str] = []
    leadership_expectations: list[str] = []

    # Candidate fit (from Gap Analyzer — deterministic)
    candidate_strengths: list[str] = []
    candidate_gaps: list[str] = []

    # Interview focus (from evidence + tools)
    likely_interview_topics: list[str] = []
    priority_competencies: list[str] = []

    # Provenance (grounding, not raw chunks)
    source_references: list[SourceReference] = []
```

Mapping from existing career outputs:

| PreparationContext field | Source |
| --- | --- |
| target_role, seniority, required_skills, key_responsibilities, leadership_expectations | `tools.schemas.RoleRequirements` (Job Description Analyzer) |
| candidate_strengths, candidate_gaps | `tools.schemas.GapAnalysisResult` (Gap Analyzer) |
| likely_interview_topics | `RoleRequirements.likely_interview_themes` + retrieved evidence |
| priority_competencies | Gap Analyzer priority gaps |
| source_references | `Citation` list from the RAG chain (title/source/page only) |
| job_description | sanitised input (never raw retriever text) |

Consumed by Interview Practice to seed a role-specific practice session
("Practise this role") via `integration/handoff.py`.

## Why this shape

- Keeps Career Intelligence **independently reviewable** for the sprint (it stays
  a cohesive `src/career/` package with all its tests).
- Keeps Interview Practice's production features intact under `src/interview/`.
- Confines coupling to one small, typed contract — safe to test and to reason
  about, and impossible to leak framework objects across the boundary.
