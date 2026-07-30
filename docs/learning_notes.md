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

---

## Phase 4 — Security and privacy guards

### Concepts introduced

- **Defence in depth, and honesty about limits.** The guard is deterministic
  and best-effort — regexes, weights and length caps — not perfect or
  production-grade. It reduces obvious risk; the real boundary is
  architectural (untrusted text stays in the user message, wrapped as data).
- **Sanitise vs validate.** `sanitize_text` cleans (null bytes, control and
  zero-width characters, whitespace) without changing meaning; `validate_field`
  enforces required-ness and named length limits.
- **Reject, don't truncate.** Oversized input raises a safe error rather than
  being silently shortened, so the user is never misled about what was sent.
- **Normalise before matching.** Injection detection maps leetspeak and strips
  the text to alphanumerics, so `i g n o r e`, `i.g.n.o.r.e` and `1gn0re` all
  collapse to the same form — defeating simple obfuscation without relying on
  exact phrases.
- **Weighted scoring with three outcomes.** Multiple indicators contribute
  weights; the total maps to allow / allow_with_warning / block. A single
  strong signal blocks; milder ones accumulate.
- **Avoiding false positives.** Indicators are phrase-shaped (`system` near
  `prompt`), so benign technical words (*system*, *execute*, *administrator*)
  score zero. This is why the guard was tuned and tested against false-positive
  candidates, not only attacks.
- **Scope defaults to allow.** Interview practice is broad, so the scope guard
  blocks only clearly malicious intents and lets everything else through.
- **Output is untrusted too.** The output guard checks JSON validity/schema,
  size, system-prompt leakage markers and secret-like patterns before a
  response is used.

### Important files

- `src/security.py` — all six controls (validation, injection detection, scope
  guard, wrappers, output guard, privacy notices).
- `tests/test_security.py` — required cases plus false-positive candidates.
- `docs/security.md` — threat model, each control, and the stated limitations.
- `src/constants.py` — per-field length limits, output cap and injection
  thresholds.

### Decisions made

- **Thresholds and length limits live in `constants.py`**; indicator patterns
  and weights live with the detector in `security.py`.
- **The guard never claims to be complete.** The module docstring and
  `docs/security.md` both state its limits explicitly.
- **Wrappers frame, they do not sanitise.** They mark content as data-only;
  cleaning is `validate_field`'s job — the layers are complementary.

### Questions I should be able to answer

1. Why is rejecting oversized input safer than truncating it?
2. How does normalisation defeat obfuscated injection without exact-phrase
   matching?
3. Why does a single strong indicator block while others only warn?
4. How does the guard avoid flagging benign technical language?
5. Why does the scope guard default to allow?
6. What can the output guard catch, and what can it not?
7. Why is it important to state that this guard is not production-grade?

### My reflections

-
-
-

---

## Phase 5 — OpenRouter integration, usage and pricing

### Concepts introduced

- **A thin, typed HTTP client.** `openrouter_client.py` wraps one endpoint. It
  returns a `ChatResult` dataclass, so the rest of the app works with typed
  fields, not raw dictionaries.
- **Explicit timeouts.** A short connect timeout fails fast on network trouble;
  a longer read timeout tolerates slow model responses. Both are set on an
  `httpx.Timeout`.
- **Exhaustive error mapping.** Every failure mode (missing key, 400/401/402/
  429, 5xx, timeout, network, invalid JSON, empty choices, missing usage,
  unsupported parameter) maps to its own exception with a safe message. The UI
  can then explain exactly what happened.
- **Graceful degradation.** If usage is missing, the content is still returned
  with `usage_available=False` rather than throwing away a good answer.
- **Privacy in logging.** By default the client logs nothing. Debug mode logs
  only request ID, model, duration and a coarse status category — never
  headers, keys or message content.
- **Capability-aware requests.** `response_format` (structured output) is only
  sent when the model's `supported_parameters` include it; otherwise the client
  refuses before making a call.
- **Testing HTTP without a network.** `httpx.MockTransport` lets tests script
  responses (and raise timeouts/network errors) with no real request and no
  live key.
- **Cost precedence and Decimal.** Cost is reported → calculated → unavailable.
  Calculations use `Decimal` so tiny per-token prices sum exactly; the value is
  rounded only when converting to a float for storage/display.
- **Pricing is data, not code.** Prices and `supported_parameters` come from the
  live `/models` endpoint, cached once per session — never hard-coded.

### Important files

- `src/openrouter_client.py` — the typed client and its exceptions.
- `src/pricing_service.py` — metadata fetch/cache, cost resolution, session
  totals.
- `src/models.py` — adds `ModelPricing`; reuses `UsageRecord`.
- `src/config.py` — adds base URL, timeouts, referer/title and endpoint URLs.
- `tests/test_openrouter_client.py`, `tests/test_pricing_service.py` — fully
  mocked; no live calls.

### Decisions made

- **Non-streaming first**, as required — simpler to reason about and to test.
- **Reported cost preferred** over our own estimate; estimates are clearly
  labelled and never presented as the final bill.
- **`test_connection()` is a real but tiny request**, meant to run only behind
  a user-pressed button, so we never make surprise paid calls.
- **The client never logs sensitive data**; the debug surface is a small,
  explicit dataclass.

### Questions I should be able to answer

1. Why are explicit connect and read timeouts better than one overall timeout?
2. How does the client keep credentials and content out of the logs?
3. Why is `response_format` gated on `supported_parameters`?
4. What is the cost precedence, and why prefer the reported cost?
5. Why use `Decimal` for cost, and where is it converted to float?
6. Why is pricing fetched from `/models` instead of hard-coded, and why cache?
7. How do the tests exercise timeouts and errors without a network or API key?

### My reflections

-
-
-

---

## Phase 6 — Application services and interview orchestration

### Concepts introduced

- **Services as thin orchestrators.** Each use case (strategy, next question,
  evaluation, report) wires together existing modules — registry, prompts,
  security, client, parser, pricing — and returns a validated object plus a
  `UsageRecord`. The services hold no business rules the models don't.
- **A shared generation pipeline.** `BaseGenerationService._generate` runs the
  same steps for every task; subclasses only choose the task, schema and
  message context. Less duplication, one place to reason about safety.
- **Dependency injection.** The client and pricing service are constructor
  arguments, so tests pass fakes with canned model results — no live key, no
  network — and there is no global mutable state.
- **Controlled domain errors.** `ServiceInputError` and `ModelResponseError`
  wrap every failure (bad input, blocked injection, API error, unparseable
  output) so callers never see a raw exception or stack trace.
- **Safe parsing with one repair round.** `response_parser` strips code fences,
  parses JSON with `json.loads` (never `eval`/`exec`), validates through the
  right Pydantic model, and — only once — lets an injected repair callable ask
  the model to fix its JSON before giving up. Missing values are never invented;
  validation rejects them.
- **Task-aware prompts.** `prompts.build_task_messages` reuses the mission,
  guardrails and session parameters but swaps in a task instruction, a technique
  directive and the correct schema, so all four outputs share the same safety
  posture and system/user separation.
- **Screening context but not the answer.** Injection screening runs on context
  fields (job description, company context, background); a candidate's own
  answer is never blocked — it must always be evaluated — and is protected by
  being framed as untrusted data.

### Important files

- `src/interview_service.py` — base service + strategy and next-question cases.
- `src/evaluation_service.py`, `src/report_service.py` — the other two cases.
- `src/response_parser.py` — safe parse/validate with one repair round.
- `src/prompts.py` — extended with the task-aware API (backward compatible).
- `tests/test_*_service.py`, `tests/test_response_parser.py` — mocked model
  results only.

### Decisions made

- **Extended `prompts.py` rather than duplicating prompt logic** in each
  service; the Phase 3 evaluation techniques and their tests are untouched.
- **The primary and repair calls are summed into one `UsageRecord`**, so cost
  accounting reflects everything a use case spent.
- **`response_format` is requested only when the model supports it**, using the
  pricing service's metadata; otherwise the prompt-only JSON contract applies.
- **Made the config tests hermetic.** A real key now lives in
  `.streamlit/secrets.toml`; the `load_config` tests neutralise the Streamlit
  and `.env` lookups so they test the environment path in isolation.

### Questions I should be able to answer

1. What are the responsibilities of a service versus the modules it calls?
2. How does dependency injection make the services testable without a network?
3. Why is a candidate's answer screened differently from context fields?
4. How does the one-repair-round rule work, and why stop after the second try?
5. Why must the parser never use `eval`/`exec` or invent missing values?
6. How do all four tasks stay safe while producing four different schemas?
7. Why return domain errors instead of letting exceptions propagate?

### My reflections

-
-
-
