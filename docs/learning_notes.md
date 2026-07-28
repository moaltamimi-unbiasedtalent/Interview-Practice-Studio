# Learning notes — Interview Practice Studio

An ongoing learner record, updated at every phase. Written so I can explain
every part of this project in my Turing College review.

---

## Phase 1 — Repository and development foundation

### Concepts introduced

- **Separation of rendering and logic.** `app.py` only draws the interface;
  everything with behaviour lives in `src/`. This keeps Streamlit code easy
  to read and lets logic be tested without a browser.
- **Configuration precedence.** The API key is read from Streamlit secrets
  first (the deployment-friendly place), then from an environment variable
  (local development). There is never a default key.
- **Controlled failure.** A missing API key returns an `AppConfig` with
  `is_configured == False` instead of raising, so the UI can explain the
  problem calmly instead of crashing.
- **`SecretStr`.** Pydantic's secret type masks the key if the config object
  is ever printed or logged — defence against accidental leakage.
- **Central constants.** Approved model IDs, temperature bounds, token
  limits and input length limits live in one file so nothing drifts.
- **Session-scoped state (preview).** Streamlit reruns the whole script on
  each interaction; later phases will keep conversation state in
  `st.session_state`.

### Important files

- `src/constants.py` — approved models and safe defaults; single source of
  truth.
- `src/config.py` — key resolution and controlled missing-config handling.
- `app.py` — Phase 1 UI shell; makes no API requests.
- `tests/test_config.py` — proves the config behaviour without live calls.
- `CLAUDE.md` — the rules every phase must follow.

### Decisions made

- **Range-pinned dependencies** (e.g. `pydantic>=2.9,<3.0`) rather than
  exact pins: reproducible enough for a learning project, without freezing
  patch versions.
- **`pyproject.toml` for metadata and pytest config only**; installation
  uses `requirements.txt` — the simplest setup a Sprint 1 learner can
  explain.
- **Secrets-first key loading** because Streamlit deployments use
  `secrets.toml`; `.env` support kept as a convenience for local work.
- **Untrusted-input limits defined now** (job description, background,
  answer lengths) even though enforcement code arrives with the guard phase.

### Questions I should be able to answer

1. Why is business logic separated from Streamlit rendering, and what would
   go wrong if it weren't?
2. What is the exact order of API-key resolution, and why is there no
   default key?
3. Why does a missing key return a value instead of raising an exception?
4. What does `SecretStr` protect against, and what does it *not* protect
   against?
5. Why must automated tests never make live API calls?
6. Why are job descriptions treated as untrusted input even though they
   look harmless?
7. What is in `.gitignore` and why is `secrets.toml` there but
   `secrets.toml.example` not?

### My reflections

*(Space for my own notes — what surprised me, what I want to revisit, what
I'd explain differently in my own words.)*

-
-
-

---

## Phase 2 — Validated domain models and structured-output schemas

### Concepts introduced

- **Validate at the edges.** Every value crossing a boundary (UI → logic,
  model → app, request → accounting) is parsed into a Pydantic model first.
  Once validated, the rest of the code can trust the data without repeated
  defensive checks.
- **Single source of truth for choices.** Enum-like values live only in
  `src/constants.py`; `src/models.py` validates against those tuples instead
  of re-listing allowed values. Change a set once and every model follows.
- **Reusable `Annotated` field types.** `ShortText`, `FreeText`, `StrList`
  and the enum types bundle their constraints once and are applied by name.
  This keeps the models readable and the rules consistent.
- **`str_strip_whitespace` + `min_length`.** Stripping happens before length
  checks, so a whitespace-only string collapses to `""` and is rejected as
  empty — one clean rule covers both "trim" and "reject blank".
- **`extra="forbid"`.** Unknown keys raise an error rather than being ignored.
  A typo, a stale field or an injected key surfaces immediately.
- **Cross-field validation with `model_validator(mode="after")`.** Some rules
  span fields — `total_tokens` must equal `prompt_tokens + completion_tokens`,
  and a `reported` cost source requires a reported figure. These can't be
  expressed on a single field.
- **Avoiding mutable defaults.** Required lists have no default at all;
  optional context fields default to the immutable empty string. No shared
  mutable object can leak between instances.

### Important files

- `src/models.py` — the seven domain models and their shared validation base.
- `src/constants.py` — now also the home of every enum-like value set, the
  scoring bounds and the defensive size limits the models reference.
- `tests/test_models.py` — boundary and invalid-input tests proving the
  validation guarantees.

### Decisions made

- **Scores are integers with hard ranges** (0–100 overall, 1–10 rubric),
  framed in field descriptions as practice feedback, never hiring decisions.
- **Required list sections must be non-empty.** An empty section is treated
  as an incomplete model response and rejected, so downstream code always has
  something to show.
- **USD-only cost records.** OpenRouter reports spend in US dollars, so
  `UsageRecord` uppercases and accepts only `USD`.
- **No chain-of-thought field.** `interviewer_intent` is a concise rubric
  hint, not a hidden reasoning dump — consistent with the security rules.

### Questions I should be able to answer

1. Why validate data at the boundaries instead of checking it where it is
   used?
2. How does `str_strip_whitespace` combine with `min_length` to reject blank
   required fields?
3. Why do the models validate enum-like values against `constants.py` rather
   than using `Literal`?
4. What does `extra="forbid"` protect against, and when might it be too
   strict?
5. Why is a cross-field rule (token totals, reported cost) written as a
   `model_validator` rather than a field constraint?
6. Why are there no mutable default values, and what bug does that prevent?
7. How do the models stay profession-neutral and avoid storing protected
   demographic information?

### My reflections

-
-
-
