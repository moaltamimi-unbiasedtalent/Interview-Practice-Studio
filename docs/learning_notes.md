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

---

## Phase 3 — Prompt-engineering library

### Concepts introduced

- **One task, five techniques.** All five techniques target the same job —
  produce an `AnswerEvaluation` for a question + answer. Only the *method*
  block changes, which is what makes the later comparison fair.
- **System vs user separation as a security boundary.** The system message
  holds only trusted text plus fixed-vocabulary settings (persona, difficulty,
  interview types). Every free-text field the candidate types goes in the user
  message, wrapped in `<<<UNTRUSTED_REFERENCE_DATA>>>` delimiters.
- **Prompt injection defence.** The guardrails tell the model to treat the
  reference data as data only and never to follow instructions embedded in a
  job description, background or answer. Because untrusted text never reaches
  the system message, an injection string stays quarantined in the user turn.
- **No hidden chain-of-thought.** Prohibiting the model from revealing private
  reasoning is *not* the same as requesting reasoning. The structured
  procedure lists a visible six-step method but emits only the final JSON.
- **Prompts derived from the schema.** The output contract is generated from
  `AnswerEvaluation.model_fields`, so the prompt can never drift out of sync
  with the model — every schema key is listed automatically.
- **A registry over the builders.** `prompt_registry.py` pairs each stable ID
  with a name, description and use case, rejects unknown IDs with a controlled
  `UnknownPromptTechniqueError`, and exposes `selector_options()` for the
  Streamlit dropdown — the UI never touches prompt internals.

### Important files

- `src/prompts.py` — the five system-prompt builders, shared guardrails, the
  schema-derived output contract, and role-separated message assembly.
- `src/prompt_registry.py` — UI-facing catalogue and safe lookup.
- `tests/test_prompts.py` — proves the guarantees (separation, injection
  resistance, neutrality, no chain-of-thought requests, schema references,
  safe rejection).
- `docs/prompt_engineering.md` — definitions, benefits, risks, best use,
  expected effect and the fair-comparison plan.

### Decisions made

- **All five techniques emit strict JSON**, not just the "structured" ones, so
  the comparison holds the output constant and only the technique varies.
- **The few-shot example is profession-neutral** (improving an intake process)
  so the platform is not biased toward any discipline, and the improved answer
  is labelled as an example to personalise.
- **Technique IDs live in `constants.PROMPT_TECHNIQUES`** so models, prompts
  and registry all validate against one source of truth.
- **Unknown IDs raise** rather than silently defaulting — a wrong ID is a bug,
  not something to paper over.

### Questions I should be able to answer

1. Why is untrusted candidate text kept out of the system message entirely?
2. How do the prompts adapt to the session without letting free text inject
   instructions?
3. What is the difference between prohibiting chain-of-thought and requesting
   it, and how does the structured procedure stay on the right side of it?
4. Why do all five techniques produce the same schema, and how does that make
   the comparison fair?
5. How does the output contract stay in sync with `AnswerEvaluation`?
6. What does the registry protect the UI from, and how does it reject bad IDs?
7. Why is the few-shot example deliberately generic?

### My reflections

-
-
-
