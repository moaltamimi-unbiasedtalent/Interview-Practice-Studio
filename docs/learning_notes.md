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

---

## Phase 7 — Session management and conversational state

### Concepts introduced

- **An explicit state machine.** The interview moves through named states
  (SETUP, STRATEGY_READY, INTERVIEW_IN_PROGRESS, AWAITING_ANSWER, EVALUATING,
  INTERVIEW_COMPLETE, REPORT_READY, ERROR). Every operation declares which
  states it is legal from, so an out-of-order call raises
  `InvalidStateTransitionError` instead of corrupting the session.
- **Injected store.** The manager talks to Streamlit `session_state` only
  through an injected `MutableMapping`. Tests pass a plain `dict`, so the whole
  machine is exercised without a running Streamlit app and without touching
  disk.
- **Namespacing.** All data lives under one key, so it never collides with
  Streamlit's widget keys or other session values.
- **Rerun safety.** Streamlit re-runs the whole script on every interaction.
  `initialise_session` only creates data when it is missing, so chat history
  and progress survive reruns; button presses are never stored — only domain
  facts (asked / answered / evaluated / current state) drive behaviour.
- **Duplicate-call protection.** `begin_operation`/`end_operation` claim an
  in-flight slot, so a rerun cannot fire a second API call; and because
  submitting an answer moves the state to EVALUATING, a re-submitted answer is
  rejected. One answer per asked question is enforced.
- **Recoverable errors.** `enter_error` records a safe message and the state to
  return to; `recover_from_error` restores it — errors are a side-state, not a
  dead end.
- **Safe reset.** `reset_interview` builds fresh session data but carries over
  harmless developer preferences (e.g., a debug flag), so a reset never leaks
  old interview content but does not wipe the developer's settings.

### Important files

- `src/session_manager.py` — `SessionState`, `SessionData`, `SessionManager`.
- `tests/test_session_manager.py` — valid/invalid transitions, duplicate
  submissions, reset behaviour, rerun persistence, cost accumulation, recovery.

### Decisions made

- **A dataclass for session data** (not a dict) so fields are explicit and the
  reset path is obvious; it is stored as one object under the namespace key.
- **`start_new_interview` stays in SETUP**; strategy generation is a separate
  step that transitions to STRATEGY_READY, keeping each operation single-purpose.
- **Cumulative cost prefers the reported figure**, falling back to the
  calculated estimate — matching the pricing service's precedence.
- **No disk persistence** — everything is in-memory for the session only.

### Questions I should be able to answer

1. Why model the interview as an explicit state machine rather than flags?
2. How does injecting the store make the manager testable and Streamlit-free?
3. Why must `initialise_session` avoid clobbering existing data on a rerun?
4. What are the two layers of duplicate-submission protection, and when does
   each fire?
5. Why is button state never stored as session state?
6. How does reset keep developer preferences while clearing interview content?
7. How does error recovery know which state to return to?

### My reflections

-
-
-

---

## Phase 8 — Streamlit candidate experience

### Concepts introduced

- **A thin, state-routed UI.** `app.py` renders only; it reads the session
  state and calls services. Every rerun draws the view for the current state,
  so the interface is always consistent and never fires a duplicate API call.
- **Labels vs domain ids.** The UI shows friendly, profession-neutral labels;
  `ui_helpers` maps them to the validated domain ids. Keeping that mapping (and
  the report serialization) pure means it is unit-testable without Streamlit.
- **Chat as history + state.** `st.chat_message`/`st.chat_input` render the
  persisted `chat_messages`, while the real interview state lives in the
  session manager — the chat is a view, not the source of truth.
- **No network on load.** Clients and services construct lazily and model
  metadata is fetched only on an explicit connection test, so the page (and the
  AppTest smoke test) start offline and fast.
- **Testing a Streamlit app.** `streamlit.testing.v1.AppTest` runs the script
  in-process with no browser; pre-seeding `session_state` lets later states
  (strategy, report, error) be rendered and asserted offline.
- **Safe error surface.** The services already return controlled messages, so
  the UI shows those — never a stack trace, secret or system prompt — with a
  recovery path.

### Important files

- `app.py` — the single-page experience and its state router.
- `src/ui_helpers.py` — label↔id catalogues, cost formatting, report
  serialization.
- `.streamlit/config.toml` — a calm, brand-neutral theme.
- `tests/test_app_smoke.py` — AppTest startup/state smoke plus helper unit
  tests.

### Decisions made

- **Extended the shared domain taxonomy rather than remapping.** The specified
  UI taxonomy (leadership, culture and values, stakeholder or client, executive
  or board; sceptical executive, fast-paced panel) had no honest match in the
  existing ids. Extending `constants` (and adding matching persona tones in
  `prompts`) was **more accurate than mapping distinct user selections onto
  unrelated existing ids** — squashing "Executive or board" into "panel" would
  have misrepresented the candidate's choice to the model. The change is
  append-only: no id was renamed, removed or repurposed, so every prior config,
  prompt and test still holds. The two new persona tones are materially distinct
  (the sceptical executive challenges unsupported claims and asks for evidence;
  the fast-paced panel simulates multiple viewpoints with concise, fast
  questions), and `tests/test_taxonomy_extension.py` locks in validation, prompt
  mapping, tone behaviour, round-trip serialization and backward compatibility.
- **The improved example answer is shown in its own expander**, clearly
  labelled to personalise — separating it from the scored feedback.
- **Reset is confirm-gated** and rebuilds the session via the manager, so no
  interview content lingers while developer preferences survive.
- **Downloads are generated in-memory** (JSON + Markdown); nothing is written to
  disk by the app.

### Questions I should be able to answer

1. Why does the UI route on session state instead of tracking button clicks?
2. How do reruns avoid duplicate API calls and preserve chat history?
3. Why keep the label↔id mapping and serialization in `ui_helpers`?
4. How is a Streamlit app smoke-tested without a browser or network?
5. Why fetch model metadata only on a connection test?
6. How does the UI avoid leaking stack traces, secrets or the system prompt?
7. Why were the interview-type and persona vocabularies extended?

### My reflections

-
-
-

---

## Phase 9 — Prompt and model experimentation lab

### Concepts introduced

- **Fair comparison = one variable.** The prompt experiment holds the model,
  temperature, token limit, task, schema and input constant, and varies only
  the technique. The model-setting experiment holds the model and technique
  constant and varies only temperature and the token limit.
- **Safety by default.** Every experiment is chargeable, so nothing runs
  automatically: the CLIs default to a dry run that writes placeholders, and
  the Prompt Lab gates each run behind a confirmation checkbox. Live runs need
  an explicit `--run --confirm` (CLI) or a confirmed button press (UI).
- **No fabricated results.** The `evaluations/` deliverables ship with
  `PENDING` placeholders; only a real run fills the automatic metrics, and the
  seven qualitative dimensions are always scored by a human.
- **Longer ≠ better.** The reports state explicitly that response length is not
  a quality signal; techniques are judged on the evaluation dimensions.
- **Only supported parameters.** The model-setting sweep consults the model's
  `supported_parameters`; if `temperature` is unsupported, the sweep collapses
  to a single value and says so.
- **Separation of concerns in the UI.** A sidebar "View" toggle keeps the
  candidate interview simple; all experimentation lives in Prompt Lab.
- **Testing chargeable code offline.** The live runners take an injected
  evaluation service, so a fake returns canned results and the runner logic is
  fully tested without a network call; the CLIs are only exercised in their
  dry-run and refusal paths.

### Important files

- `scripts/compare_prompts.py`, `scripts/compare_model_settings.py` — the
  experiments (pure planning/serialization + gated live runners + CLIs).
- `evaluations/*.{md,json}` — placeholder deliverables (no fabricated data).
- `app.py` — the Prompt Lab view.
- `tests/test_prompt_comparison.py` — offline tests (fake service, dry-run CLIs,
  AppTest for the lab).

### Decisions made

- **Reused `EvaluationService`** for the live runs so the experiment measures
  the real pipeline, and made the runners accept an injected service for tests.
- **Placeholders are generated by the scripts' own dry run**, so the committed
  files always match what a run would produce (only the values differ).
- **The scripts add the repo root to `sys.path`** so they work both as
  `python scripts/x.py` and as importable modules for the app and tests.

### Questions I should be able to answer

1. What makes the prompt comparison a *fair* comparison?
2. Why does nothing run without explicit confirmation, and how is that enforced
   in both the CLI and the UI?
3. Why do the deliverables ship with placeholders instead of sample numbers?
4. Why is "longest answer" not treated as "best"?
5. How does the model-setting sweep avoid sending unsupported parameters?
6. How are chargeable runners tested without spending money?
7. Why is experimentation separated from the candidate experience?

### My reflections

-
-
-

---

## Phase 10 — Jailbreak and input-security evaluation

### Concepts introduced

- **Reproducible security testing.** A fixed battery of 29 cases across 16
  categories runs through the deterministic guard and records, per case, the
  expected vs actual outcome, pass/fail, risk severity, whether a model call was
  prevented, and notes — exported to an Excel workbook and a CSV.
- **Direct vs indirect injection.** Direct injection targets the assistant
  head-on; indirect injection hides the same intent inside otherwise-legitimate
  content (typically a pasted job description).
- **Guards are imperfect — and we say so.** The battery deliberately includes
  benign false-positive candidates (which must stay `allow`) and a base64
  bypass which, at Phase 10, the guard did not decode (a documented failure;
  **narrowed in Phase 11** with a bounded Base64 decoder — see below). The real
  defence is architectural: untrusted text is framed as data in the prompt.
- **Answers are flagged, never blocked.** Injection inside a candidate answer
  yields `allow_with_warning`, not `block`, because the answer must always be
  evaluated (as data). This exercises all three outcomes.
- **Blocked ⇒ no model call.** A `block` outcome rejects the input locally, so
  no chargeable request is made and hostile content never reaches the model.
- **Spreadsheet formula injection.** Cells beginning with `=`, `+`, `-`, `@`
  (or tab/CR) are prefixed with a quote so Excel/LibreOffice treat them as text;
  control characters are escaped so no null byte reaches the file.
- **Safe by default.** The runner is dry-run by default (deterministic, no
  network); live-assisted mode needs `--run-live --confirm` and only sends
  non-blocked cases. Fixtures use dummy `TEST_API_KEY`/`TEST_SECRET`; no real
  key or secret is used, printed or logged.

### Important files

- `scripts/run_jailbreak_tests.py` — the battery, guard evaluation, summary and
  writers (xlsx + csv), with formula-injection sanitisation.
- `evaluations/jailbreak_test_results.{xlsx,csv}` — the generated evidence.
- `tests/test_jailbreak_runner.py` — offline tests (no network).
- `docs/security.md` — the concepts, how-to-run and limitations.

### Decisions made

- **Guard outcomes were not weakened to raise the pass rate.** One case fails
  honestly (base64), documented as a known limitation, rather than tuning the
  guard around it.
- **The runner reuses `src.security`** so the evaluation measures the real
  guard, and takes a fixed date so results are deterministic for tests.
- **Outputs are regenerated (overwritten), not appended**, so re-running is
  idempotent.

### Questions I should be able to answer

1. What is prompt injection, and how do direct and indirect injection differ?
2. What exactly does the deterministic guard check, and in what order?
3. Why is a candidate answer flagged rather than blocked?
4. Why are blocked inputs never sent to the model?
5. Why is the guard imperfect, and what is the primary defence instead?
6. How is spreadsheet formula injection prevented without losing meaning?
7. Why is live-assisted testing optional, and how is it gated?

### My reflections

-
-
-

---

## Phase 11 — Quality hardening

### Concepts introduced

- **A quality audit is a deliberate pass, not a vibe.** Fourteen areas
  (functional, generic-profession, Streamlit, state machine, request
  construction, structured output, security, pricing, prompts, accessibility,
  code quality, dependencies, artefacts, docs) were each checked, with findings
  recorded by severity in `docs/quality_report.md`.
- **Bounded, explainable security improvement.** The Phase 10 Base64 gap was
  narrowed — not by broadly decoding user content, but by decoding only
  *high-confidence, standalone* Base64 segments (strict length window, valid
  padding, printable UTF-8) and re-scanning them with the *same* injection
  scanner. Decoded bytes are never executed. Benign Base64 (sentences, ids,
  hashes, binary blobs) is not flagged, so there are no material false
  positives — verified by tests.
- **Strengthening ≠ gaming the pass rate.** JB-22 now blocks because the guard
  genuinely improved, and the residual risk (other encodings, nested/split
  Base64) is documented honestly. The guard is still not claimed to be perfect.
- **Generic-profession proof.** A parametrised test drives ten professions
  (developer, accountant, nurse, electrician, ops manager, marketing director,
  teacher, compliance manager, sales manager, CEO) and asserts the system
  prompt stays neutral while the role travels in the user message — evidence the
  app hard-codes no single discipline.

### Important files

- `src/security.py` — bounded Base64 decode-and-rescan in `detect_injection`.
- `scripts/run_jailbreak_tests.py` + regenerated `evaluations/jailbreak_*`
  (JB-22 now blocks; 29/29).
- `tests/test_security.py` (Base64 regression cases),
  `tests/test_generic_professions.py` (new).
- `docs/quality_report.md` (new), `docs/security.md`, `docs/learning_notes.md`.

### Decisions made

- **Improved the guard rather than retaining the gap**, because the improvement
  met every safety criterion (bounded size, high-confidence only, no execution,
  reuses the scanner, no material false positives, learner-understandable).
- **No new lint/format tool was installed** just for appearance; static checks
  used compile, import and manual AST scans already available.
- **Existing security rules were not weakened** to raise any pass rate.

### Questions I should be able to answer

1. What did the quality audit cover, and how are defects triaged by severity?
2. How does the bounded Base64 decoder avoid false positives, and why is it
   safe (no execution, size-limited, high-confidence only)?
3. Why is improving the guard different from weakening it to pass a test?
4. What residual encoding risks remain after Phase 11?
5. How do the tests prove the app is profession-neutral without live calls?
6. Why keep the architectural (data-framing) defence as primary even after the
   Base64 improvement?
7. Why avoid installing extra tooling during a hardening pass?

### My reflections

-
-
-

---

# Consolidated learner summary (Phase 12)

A single-page recap of the whole project, followed by reflection prompts you
must answer **in your own words** before submission. This section deliberately
contains no personal reflections written for you.

## Main concepts learned

- Building an LLM application as small, testable layers rather than one script.
- Prompt engineering: five techniques over one task and schema.
- Structured output with Pydantic validation and safe parsing.
- Deterministic, best-effort security guarding vs architectural defence.
- Streamlit session-state and an explicit interview state machine.
- Token/cost accounting with a reported→calculated→unavailable precedence.
- Reproducible, gated experiments and honest evaluation artefacts.

## Architecture decisions

- Thin UI (`app.py`) vs logic in `src/`; dependency injection for testability.
- A prompt registry as the single catalogue for UI and experiments.
- Secrets via Streamlit secrets → env fallback, masked, never a default key.
- No LangChain/RAG/agents/DB in Sprint 1 — simpler is clearer and explainable.

## Prompt-engineering lessons

- Same task + schema + inputs is what makes a technique comparison fair.
- A "visible procedure" is not the same as hidden chain-of-thought.
- Improved answers must be labelled examples, never fabricated achievements.

## Model-setting lessons

- Temperature and max tokens are session settings; only send supported params.
- gpt-5-mini metadata did not advertise `temperature`, so the sweep collapsed —
  a real, recorded observation, not an assumption.

## Structured-output lessons

- Validate, never trust; reject invalid scores and missing fields.
- One repair attempt, then a controlled error — no `eval`/`exec`, no loops.

## Security lessons

- Direct vs indirect injection; blocked input is never sent to the model.
- Answers are warned, not blocked, because they must still be evaluated.
- Bounded Base64 decode-and-rescan narrows — but does not close — encoding risk.
- Spreadsheet formula injection is a real export risk with a simple mitigation.

## Testing lessons

- Deterministic, mocked tests keep the suite fast, free and network-safe.
- Live behaviour needs explicit, gated, chargeable paths.

## Streamlit state-management lessons

- Reruns re-execute the whole script; state must persist and calls must be
  de-duplicated (state machine + in-flight guard).

## Cost-reporting lessons

- Prefer the provider's reported cost; label estimates; never double-count.

## Mistakes / issues encountered and how they were resolved

- **Base64 injection gap (JB-22):** documented at Phase 10, then narrowed at
  Phase 11 with a bounded decoder + tests. Resolution: strengthen the guard, do
  not weaken the test.
- **Experiment run captured no metrics:** the committed comparison files show a
  completed-but-errored run. Resolution: documented honestly; re-run with a
  funded key to populate figures (not fabricated).
- **Config tests not hermetic:** a local secret leaked into `load_config` tests;
  resolution: the tests neutralise the secret readers.

## Concepts I should be able to explain

Roles (system/user/assistant); temperature; max tokens; model choice;
structured JSON; Pydantic validation; Streamlit session state; prompt
injection; secret management; usage/cost; deterministic vs live tests; the
state machine; why scores are advisory; duplicate-call prevention; and why
Sprint 1 excludes RAG/LangChain.

---

## Reflection prompts — *Complete this in your own words before submission*

Write your own answers below each prompt. Keep them honest and specific; the
reviewer wants **your** understanding, not a generated summary.

1. In one paragraph, what does this app do and who is it for? *(Complete this in
   your own words before submission.)*
2. Which part of the codebase did you find hardest to understand, and how did
   you get comfortable with it? *(Complete this in your own words.)*
3. Explain, without looking, how a single answer flows from the chat box to a
   validated `AnswerEvaluation`. *(Complete this in your own words.)*
4. Which prompt technique would you choose for production and why? What evidence
   would you want first? *(Complete this in your own words.)*
5. Describe one security limitation you can explain confidently to a reviewer.
   *(Complete this in your own words.)*
6. What did you learn about testing code that calls an external API?
   *(Complete this in your own words.)*
7. If you had one more week, what would you change and why? *(Complete this in
   your own words.)*
8. What did AI assistance help with, and what did you make sure you understood
   yourself? *(Complete this in your own words.)*

---

## Phase 13 — Manual browser acceptance testing (preparation)

### What this phase is

Preparation and structure for **human** acceptance testing in a real browser —
not automated. It produces a reproducible test plan; the actual PASS/FAIL
results and screenshots are recorded by the learner.

### Concepts introduced

- **Acceptance testing vs unit testing.** Automated tests prove components work
  in isolation (mocked, offline); acceptance testing proves the whole app works
  for a real user in a browser, including the live model path.
- **Test IDs and evidence.** Each of the 107 cases has an ID, exact steps, an
  expected outcome, a status (starting at NOT RUN) and an evidence slot, so a
  reviewer can reproduce and audit each result.
- **Requirement tagging.** Every case is tagged `[live]`, `[browser]`,
  `[offline]`, `[auto]` or `[mock]`, which shows which results need spend, which
  are already backed by automation, and which are pure inspection.
- **Cost- and safety-aware testing.** Failure cases (401/402/429/timeout) are
  verified with existing tests or a temporary invalid key — never by exhausting
  or overloading a real account.
- **Honest evaluation status.** The prompt/model-setting experiment files still
  record errored runs; this is preserved as a documented gap, not fabricated.

### Important files

- `docs/manual_acceptance_test.md` — the 107-case plan + "instructions for Mo".
- `docs/screenshots/README.md` — the eight-screenshot checklist.

### Questions I should be able to answer

1. What is the difference between the automated suite and acceptance testing?
2. Which acceptance tests need live API access and why?
3. How is failure behaviour verified without abusing the provider?
4. Why do product fixes belong in a later phase, not the testing phase?

### Reflection prompt — *Complete this in your own words before submission*

- After running the browser tests, summarise what worked, what failed, and what
  you would fix first. *(Complete this in your own words before submission.)*

---

## Phase 14 — Interview Deep Dive (branching)

### Concepts introduced

- **A bounded feature, not an agent.** Branching lets the candidate explore a
  question more deeply (up to two levels) then return — deliberately bounded to
  avoid runaway tokens, confusing navigation and uncontrolled state.
- **Sub-state machine.** Two new states (`BRANCH_AWAITING_ANSWER`,
  `BRANCH_EVALUATING`) plus a `branch_active` flag extend the existing machine
  without replacing it; main progress operations are blocked while branching.
- **Isolation of main progress.** A branch never touches
  `current_question_number` or the main lists, so "Question 2 of 6" stays
  correct — proven by tests.
- **Authoritative overrides before validation.** The parser can patch
  caller-owned fields (branch id, parent, depth, mode) into the model's JSON
  *before* validation, so a branch is always correctly anchored regardless of
  what the model returns — and an out-of-range model depth can't slip through.
- **Reuse over reinvention.** Branch questions flow through the same
  `_generate` pipeline; branch answers reuse `AnswerEvaluation`; branch cost is
  recorded once, guarded against Streamlit reruns.

### Important files

- `src/session_manager.py` — branch states, fields, methods, guards.
- `src/interview_service.py` — `generate_branch_question`.
- `src/models.py` — `BranchQuestion`; `src/prompts.py` — `TASK_BRANCH`.
- `app.py` — Deep Dive UI. `tests/test_branching.py` — 29 tests.

### Decisions made

- **Extended the state machine** rather than tracking branches in loose globals.
- **Overrides applied pre-validation** in the parser (a small, reusable change)
  instead of trusting or post-patching model linkage fields.
- **Report integration is additive** — `generate_report(..., branch_summaries)`
  defaults to empty, so existing behaviour and tests are unchanged.

### Questions I should be able to answer

1. How does a Deep Dive differ from a normal follow-up question?
2. What stops branching from advancing or completing the main interview?
3. How is branch depth bounded, and where is that enforced?
4. Why override linkage fields before validation rather than after?
5. How are branch usage and cost prevented from double-counting on reruns?
6. How does security apply to a branch answer?

### Reflection prompt — *Complete this in your own words before submission*

- Explain, in your own words, why branching keeps the main interview intact and
  how you would demo that to a reviewer. *(Complete this in your own words.)*

---

## Fix — Control reasoning in normal interview generation

### The defect (demonstrated live)

A running interview reached the error view with:
*"OpenRouter response contained no assistant content (finish_reason: length)."*

The cause is the same reasoning-token behaviour already handled for the
connection test: GPT-5 models spend output tokens on internal reasoning before
emitting visible text. With reasoning left at the model default, a structured
call (e.g. strategy generation) exhausted its completion budget on reasoning
and returned an empty message with `finish_reason=length`. This is exactly the
risk flagged earlier; the screenshot proved it, so the fix was applied to
normal generation, not just the connection test.

### The fix

- `BaseGenerationService._call_model` now requests
  `reasoning={"effort": constants.DEFAULT_REASONING_EFFORT}` (`"minimal"`) on
  every model call (primary and JSON-repair), for all use cases (strategy,
  question, evaluation, report, branch).
- The OpenRouter client already gates `reasoning` on the model's advertised
  `supported_parameters`, so it is sent only to reasoning-capable models and
  silently dropped for the rest. The service passes the model's supported
  parameters into the call, so no non-reasoning model ever receives it.
- New constant `DEFAULT_REASONING_EFFORT = "minimal"` documents the intent in
  one place.

### Trade-off

Minimal reasoning slightly reduces the depth of internal deliberation, but the
prior behaviour returned *no answer at all* on long structured tasks. A
reliable, budget-respecting answer is strictly better here; users can still
raise the max-output-tokens setting for longer outputs.

### Questions I should be able to answer

1. Why does a reasoning model return empty content with `finish_reason=length`?
2. Where is `reasoning` gated so non-reasoning models never receive it?
3. Why apply the effort control in the service rather than the client?
4. What is the trade-off of forcing `effort=minimal`, and why is it acceptable?

### Follow-up — output-budget floor

A second run failed with *"The model response could not be parsed after one
repair attempt"* because **Maximum output tokens** had been set to 256. With
reasoning now controlled the model *does* produce text, but 256 tokens is too
small to hold a full strategy/report JSON, so the object was truncated and the
(equally capped) repair round also failed.

Fix: raised `MIN_OUTPUT_TOKENS` from 64 to 512 so the app can no longer be put
into a guaranteed-to-truncate state; the default (1024) remains the recommended
value for the larger strategy and report tasks. The model-settings experiment
grid now derives its "concise" budget from `MIN_OUTPUT_TOKENS`.

Reviewer question: why is a single global token budget a foot-gun across tasks
of very different output sizes, and what would a per-task budget look like?

### Follow-up — parse robustness and diagnostics

A later run failed to parse even with a large token budget (960 output tokens,
no truncation), so the model returned a full response that was not directly
loadable as the required JSON object. Two changes make this both more robust
and diagnosable:

- **Balanced-object extraction.** `parse_json_object` now falls back to
  extracting the first complete top-level `{...}` object (ignoring braces
  inside strings) when the whole response is not valid JSON. This tolerates a
  short preamble or trailing note around an otherwise-valid object without
  loosening validation of the object's contents. `extra="forbid"` on the
  models is unchanged, so unknown/injected fields are still rejected.
- **Concrete failure reason + server-side logging.** The final parse error now
  includes the specific reason (e.g. which fields failed, or "not valid JSON"),
  and the service logs a truncated copy of each raw attempt to the console so a
  formatting failure can be inspected. Model output is not a secret and the
  output guard has already screened it; API keys are never logged.

Reviewer question: why extract a balanced object rather than loosening the
schema to accept extra fields, and what would each choice cost in safety?

### Follow-up — tolerant (but closed) enum validation

With diagnostics in place, the real failure surfaced clearly: an
`InterviewQuestion` was rejected on `difficulty`. The model returns natural
surface variants — `medium` for `moderate`, US `behavioral` for `behavioural`,
`Case Study` for `case_study` — which exact, case-sensitive matching refused,
and the repair round (which lists field *names*, not allowed *values*) could
not recover.

Fix: the enum factory `_make_enum_type` now normalises case, whitespace and
hyphens, and consults a small per-field synonym map, always returning the
**canonical** value. The vocabulary stays closed — an unmappable value is still
rejected — so this adds tolerance without weakening the injection defence or
inventing values. Only the two enums the model fills in freely (question
`difficulty` and `question_type`) carry synonym maps.

Reviewer question: why is normalising to a canonical value safer than either
(a) accepting any string or (b) failing on every surface variant?

### Follow-up — lenient enums for model-invented classification fields

The next failure was `question_type`: the model returns open-ended category
labels (e.g. `system_design`, `motivational`) that no fixed synonym list can
fully anticipate. Chasing every label with synonyms is a losing game, and
failing the whole interview over a descriptive tag is the wrong trade-off.

Design decision — separate **input** enums from **model-output** enums:

- **Input enums stay strict.** `InterviewConfiguration` difficulty/type still
  reject any unknown value (injection defence and configuration integrity are
  unchanged). A test asserts this explicitly.
- **Model-output classification enums are lenient.** A new
  `_make_lenient_enum_type` coerces an unmappable `question_type` or generated
  `difficulty` to a safe in-vocabulary default (`behavioural` / `moderate`) and
  logs the coercion, so the interview continues. These types (`QuestionType`,
  `ModelDifficulty`) are used only in generated output, never on input.
- **Prompt guidance** now tells the model to set `question_type` to one of the
  session's interview types and `difficulty` to exactly easy/moderate/hard,
  which keeps the recorded label accurate and makes coercion rare.

Reviewer question: why is it correct to coerce a model's descriptive tag but
wrong to coerce a user's configuration value? (Trust boundary: output is ours
to normalise; input must be validated, not silently changed.)

### Follow-up — ignore surplus keys in model output (not input)

The evaluation step then failed on `stronger_answer_structure` — a key the
model *added* that is not in `AnswerEvaluation`. The schemas used
`extra="forbid"`, so any well-meant surplus field failed the whole response.
This is the same trust-boundary lesson as the enums: strict for input, tolerant
for model output.

Fix: a new `_GeneratedModel` base sets `extra="ignore"`, and the five
model-parsed schemas (`InterviewStrategy`, `InterviewQuestion`,
`AnswerEvaluation`, `FinalInterviewReport`, `BranchQuestion`) inherit it. Input
and internal models (`InterviewConfiguration`, `ModelSettings`, `UsageRecord`,
`ModelPricing`) keep `extra="forbid"`. Required fields are still validated, so
missing or malformed values are still rejected and nothing is invented; a stray
field is simply dropped and never reaches the UI (the no-hidden-reasoning guard
still holds because a `chain_of_thought` key is dropped, not surfaced).

Reviewer question: what is the difference in risk between an unexpected key in
*user input* versus in *model output*, and why does that justify different
`extra` policies?

### Root cause and the durable fix — generation retry

All the parse errors shared **one** root cause: the app enforces a strict,
validated schema on a *probabilistic* language model. The same request can
return a clean object one moment and an off-shape one the next. Each earlier
error was that single event surfacing at a different point (no text, truncated,
prose-wrapped, an off-vocabulary enum, a surplus key). Those five structural
causes are now fixed, but any *new* one-off deviation (a too-long field, a
missing key, a bad number) could still fail a single attempt.

Durable fix: `_generate` now retries the whole generation up to
`GENERATION_MAX_ATTEMPTS` (2) times. Each attempt is a **fresh** request — not
just a repair of the same bad text — so because model output varies run to run,
a one-off malformed generation self-heals and the user never sees an error.
Guarantees kept: validation stays strict (an always-invalid value such as an
out-of-range score is still rejected — a test proves it), attempts are bounded
so a broken model cannot loop, a safety block is raised immediately and never
retried, and cost accounting bills every call made across all attempts.

Reviewer question: why is retrying with a fresh generation more effective than
only repairing the same response, and what stops the retry from hiding a real,
persistent defect?

### Follow-up — consistency and robustness polish

Three small, requested improvements:

1. **Difficulty label aligned to the vocabulary.** The dropdown showed "Medium"
   while the canonical value is `moderate`. Renamed the label to "Moderate", so
   the UI, the prompt and the data all use one word. (The synonym bridge still
   maps a stray `medium` from the model, but the app no longer introduces the
   mismatch itself.)
2. **Full interview-type vocabulary in the UI.** The dropdown offered 9 of the
   12 types; added "Situational", "Competency-based" and "Portfolio review" so
   every vocabulary value is selectable.
3. **More generous self-healing.** `GENERATION_MAX_ATTEMPTS` raised from 2 to 3,
   giving one more fresh generation before an error can surface. Still bounded.

### Follow-up — flatten text fields the model returns as a list/object

The evaluation kept failing on `stronger_answer_structure`. That field is a
*real, required* free-text (string) field — not a surplus key — so `extra=ignore`
never applied. The model was answering it with a **list of steps** (STAR-style)
or a small object, which fails the "must be a string" rule *consistently*, so
the fresh retries could not help either.

Fix: `_GeneratedModel` now runs a `mode="before"` validator that flattens a
list/object into a readable string, but only for fields the schema types as a
plain string. Genuine list fields (`strengths`, `improvement_areas`, …) are
untouched, and every required field is still validated. This closes the last
common shape mismatch in model output.

Root-cause summary for the whole series: a strict schema meeting probabilistic
output. The fixes fall into three families — content/budget (reasoning control,
token floor, retries), shape (JSON extraction, ignore surplus keys, flatten
text), and vocabulary (tolerant + lenient enums). Input validation stayed
strict throughout; only *model output* was made tolerant.

### Token-budget audit — five confirmed issues fixed

A focused audit of the token-budget paths confirmed all five suspected issues.
Each fix is small and preserves the existing architecture (no new service layer,
no frameworks).

1. **Unbounded prompt-history growth.** `generate_next_question` sent every
   prior answer (each up to `MAX_ANSWER_CHARS`) on every turn — up to ~120k
   characters by question 20 — risking context-window overflow. Fix: keep all
   (short) previous questions and all compact evaluation summaries, but bound
   the full answer texts to the most recent `MAX_HISTORY_ANSWERS` (4).
2. **Truncation ignored + futile retries.** `finish_reason` was recorded on
   `ChatResult` but never acted on; a truncated (`length`) response failed
   parsing and was retried with the *same* budget. Fix: on a parse failure
   where any response was truncated, raise a distinct, actionable error
   ("increase Maximum output tokens") and stop — no same-budget retry.
3. **Model limits ignored.** `PricingService` read pricing and supported
   parameters but not `context_length` / `top_provider.max_completion_tokens`.
   Fix: small read-only accessors for both, and the service now caps the
   requested `max_tokens` at the model's completion limit (never raising it).
4. **Answer length not enforced.** Streamlit chat answers went straight to
   session state and the API without the `MAX_ANSWER_CHARS` check. Fix: both
   handlers validate via `security.validate_field("candidate_answer")` before
   any state change, and the inputs carry `max_chars`. (Injection screening is
   still deliberately not applied to answers.)
5. **Repair unguarded + failed calls unbilled.** The automatic repair response
   bypassed the output safety scan, and a fully-failed generation recorded no
   usage. Fix: the repaired response is now safety-scanned like the primary,
   and every billed call is recorded even when all attempts fail.

### Regression fix — stale cached PricingService after hot reload

Symptom: `AttributeError: 'PricingService' object has no attribute
'max_completion_tokens'` from `interview_service._effective_max_tokens`.

Root cause (not an invented method): the accessor *does* exist on the current
class, but `app.get_pricing_service()` caches the instance in
`st.session_state`. After a code hot-reload the cached instance still points to
the pre-patch class object, which lacks the new accessor. It is a stale-instance
problem, not a missing method.

Fix (two small, safe parts):
- `_effective_max_tokens` resolves the accessor with `getattr(..., None)` and
  falls back to the configured `settings.max_tokens` if it is absent or returns
  no positive limit — so a missing accessor can never raise into Streamlit.
- `get_pricing_service()` rebuilds the cached service when it is not an instance
  of the current class (`isinstance` fails across a reload), so the accessor is
  available again without a manual restart.

The cap still only ever *lowers* the request to a model's advertised limit and
is a no-op when metadata omits one.

---

## Phase 15 — product foundation hardening

Work on branch `product/full-fledged-interview-app` (not `main`).

### Why strict JSON Schema replaced most repair logic

The Sprint 1 code coped with imperfect model output defensively: a `json_object`
hint, manual JSON extraction, Pydantic validation, a model-based repair round,
and (later) several fresh generations. That is the right approach when the model
can return *any* shape. But OpenRouter can ask a capable provider to **enforce**
a strict JSON Schema, so the returned text is guaranteed to be an object of the
right shape. Once enforcement is available, repeatedly asking a model to "fix its
JSON" is wasted effort and extra billable requests. So:

- When metadata advertises `structured_outputs`, we send a strict schema
  generated from the Pydantic model (no duplication) and **skip repair** — a
  schema violation then means a genuine provider/model issue, handled by a single
  controlled fallback to the defensive path.
- When enforcement is unavailable, we keep the defensive parser with exactly
  **one** repair round (not three fresh generations).

Validation is never weakened: the Pydantic model still validates every returned
object, so lenient coercions (text flattening, enum synonyms) and strict bounds
(scores, list sizes) still apply.

### Other decisions

- **Capability layer over metadata.** `ModelCapabilities` answers "does this
  model support temperature / reasoning / structured outputs?" from
  `supported_parameters`, so the UI and services never assume a parameter works.
- **One transient retry at the HTTP boundary**, never stacked with the
  application retries, so a single action stays within a small, documented
  request ceiling.
- **Safe-metadata-only logging** so no candidate content or model body is ever
  written to logs.
- **pyproject is the dependency source of truth**; `requirements.txt` mirrors the
  runtime pins and dev tools live under `optional-dependencies.dev`.

### Review questions

1. When is strict JSON Schema used, and why does it remove the need for repair?
2. What happens when a provider cannot enforce the requested schema?
3. What is the maximum number of API requests one user action can make?
4. Which request parameters are gated by metadata, and where is that enforced?
5. What exactly may and may not appear in a generation-failure log line?

---

## Phase 16 — recorded voice answers + speech-to-text

Branch `product/full-fledged-interview-app` (continued).

### What and why

Candidates can now answer by voice as well as by typing. A provider-agnostic
`SpeechTranscriptionService` keeps the interview services decoupled from any one
speech vendor: the first provider is Google Cloud Speech-to-Text V2 (Chirp 3),
but adding another later needs no change to evaluation or the app flow. The
Google SDK is imported lazily and the client is injectable, so the app runs
(and every test passes) without the SDK or credentials.

Key decisions:
- **Verbatim transcripts** — never rewritten — so evaluation sees the real
  answer. The candidate reviews/edits the transcript before submitting; a
  transcription is never auto-submitted.
- **Audio is never persisted** and never logged; only transcript text and
  numeric metrics are kept. The privacy notice is therefore truthful.
- **Cost separation** — speech usage is an `ExternalServiceUsage` (audio
  seconds) tracked apart from LLM tokens; a dollar cost is shown only when a
  real rate is known.
- **Graceful degradation** — no credentials ⇒ voice unavailable, text still
  works, no crash.

### Review questions

1. How does the app stay independent of the speech provider?
2. Where is raw audio, and why can we claim it is not saved?
3. Why must the transcript be verbatim and candidate-editable before submission?
4. How is transcription cost kept honest and separate from LLM cost?
5. What happens when speech credentials are missing?

---

## Phase 17 — real-time AI interviewer (Gemini Live, experimental)

Branch `product/full-fledged-interview-app` (continued). Adds a third optional
mode (Live Interview) without replacing Text or Voice practice.

### Key decision: one engine, two roles

OpenRouter stays the single interview intelligence (questions, evaluation, Deep
Dive, report); Gemini Live is only the real-time voice *interface*. This avoids
two competing engines: `LiveInterviewService` delegates every substantive step
back to the existing services and adds only token minting, the non-secret
browser config, and separate usage accounting.

### Security: ephemeral tokens

The permanent Gemini key must never reach the browser, so the backend mints
short-lived ephemeral tokens and hands the browser only those. The key is a
`SecretStr`, tokens are masked and never logged, expiry is explicit, and a test
proves the permanent key never appears in the browser config.

### Explicit turn state machine

`LiveTurnState` replaces loose booleans with an auditable lifecycle, and
`ReconnectPolicy` bounds reconnection. Barge-in is modelled as a validated
transition that also flags stale interviewer audio for discard.

### Graceful degradation

The frontend component isn't built in CI, so `is_available()` returns `False`
and the app falls back to Voice/Text without losing answers — the same path used
if a live session fails at runtime.

### Review questions

1. Why is OpenRouter still the only interview engine, and how is that enforced?
2. How does the permanent Gemini key stay off the browser?
3. What states make up a live turn, and how is barge-in handled?
4. What stops reconnection from looping forever?
5. What happens when live mode is unavailable mid-interview?

---

## Phase 18 — answer timing + conversational coach

Branch `product/full-fledged-interview-app` (continued). Adds delivery/pacing
coaching without turning the interview into a timed exam.

### Key decisions

- **Explainable durations.** `recommended_seconds = target_words / WPM * 60`,
  clamped to [30, 300] s, with target words varying by question type and
  difficulty — no magic 120-second default. Deep Dive uses a shorter target.
- **Guidance is isolated from scoring.** Timing lives in its own module, is
  displayed separately ("Delivery & pacing"), and never touches
  `AnswerEvaluation`. Exceeding the recommended time only nudges; it never stops
  the candidate or lowers a score.
- **Honest metrics.** Pause/segment metrics require voice-activity data (live);
  recorded voice reports duration-based metrics only, and typed answers report
  none — nothing is fabricated.
- **Plain language.** Delivery notes avoid medical/psychological framing.

### Review questions

1. How is the recommended duration computed, and why does it vary by question?
2. Why does timing live outside the evaluation/scoring path?
3. What is a "meaningful pause", and when can pauses be measured at all?
4. What do typed answers contribute to delivery metrics? (Nothing.)
5. What does the live timer do at 100% and at 120%?
