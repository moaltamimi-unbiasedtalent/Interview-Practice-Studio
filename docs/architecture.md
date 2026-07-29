# Architecture — Interview Practice Studio

## Product objective

Help any candidate — in any profession, industry, career level or interview
type — prepare for interviews by practising realistically against an LLM
interviewer and receiving structured, actionable feedback on every answer.
The product is deliberately generic: nothing in prompts, scoring or examples
assumes a specific domain.

## User journey

1. The candidate opens the app and optionally pastes a job description and a
   short background summary.
2. They choose an interview type (e.g. behavioural, technical, situational),
   career level, model and settings.
3. The app conducts a conversational practice interview: it asks questions,
   the candidate answers, and the conversation continues naturally.
4. After each answer (or on request) the candidate receives structured
   feedback: rubric-based scores, strengths, improvements and a suggested
   revision.
5. Token usage and estimated cost are visible throughout.

## Proposed architecture

```
┌──────────────────────────────────────────────┐
│ app.py — Streamlit UI (rendering only)       │
│  session state: conversation, settings       │
└──────────────┬───────────────────────────────┘
               │ calls
┌──────────────▼───────────────────────────────┐
│ src/ — business logic                        │
│  config.py            configuration loading  │
│  constants.py         limits, models, values │
│  models.py            validated domain models│
│  prompts.py           system prompt library  │
│  prompt_registry.py   technique catalogue    │
│  security.py          security/privacy guards│
│  openrouter_client.py OpenRouter API client  │
│  pricing_service.py   usage & cost accounting│
└──────────────┬───────────────────────────────┘
               │ HTTPS (HTTPX)
┌──────────────▼───────────────────────────────┐
│ OpenRouter Chat Completions API              │
│  openai/gpt-5-mini | gpt-5-nano | gpt-5      │
└──────────────────────────────────────────────┘
```

## Main components

- **`app.py`** — Streamlit rendering only; no business logic.
- **`src/config.py`** — resolves the API key (Streamlit secrets first,
  environment fallback); returns a controlled result when missing.
- **`src/constants.py`** — the single source of truth for approved models,
  generation defaults, input length limits and every enum-like value set.
- **`src/models.py`** — validated Pydantic domain models and
  structured-output schemas. Inputs (`InterviewConfiguration`,
  `ModelSettings`), model outputs (`InterviewStrategy`, `InterviewQuestion`,
  `AnswerEvaluation`, `FinalInterviewReport`) and accounting (`UsageRecord`)
  are validated here so the rest of the app can trust its data.
- **`src/prompts.py`** — the system-prompt library: five prompt-engineering
  techniques, shared safety guardrails, a schema-derived output contract, and
  role-separated message assembly (`build_messages`).
- **`src/prompt_registry.py`** — a UI-facing catalogue mapping each stable
  technique ID to a name, description and use case, with safe rejection of
  unknown IDs and Streamlit selector options.
- **`src/security.py`** — deterministic, best-effort security and privacy
  guards: input validation/normalisation, prompt-injection risk scoring, a
  scope guard, untrusted-content wrappers, an output guard and UI-ready
  privacy notices.
- **`src/openrouter_client.py`** — a typed, non-streaming OpenRouter
  chat-completions client: Bearer auth, explicit timeouts, full error mapping,
  a safe debug mode, and a connection-test helper.
- **`src/pricing_service.py`** — usage accounting and pricing: reads live model
  pricing/metadata (cached per session), resolves reported vs calculated vs
  unavailable cost in USD, and tracks cumulative session usage.
- **Later phases** — Streamlit conversational UI and the comparison /
  jailbreak experiments.

## Domain models and structured outputs

`src/models.py` defines seven Pydantic models on a shared `_StudioModel` base
whose policy is applied everywhere: surrounding whitespace is stripped from
strings, unknown fields are rejected (`extra="forbid"`), and assignment is
validated as well as construction. Reusable field types keep the rules
consistent and readable:

- **Enum-like fields** (career level, interview type, persona, difficulty,
  response detail, prompt technique, cost source, model) are validated
  against the tuples in `src/constants.py` — models never hard-code allowed
  values.
- **Required text** rejects empty / whitespace-only content and is length
  bounded; **required lists** must be non-empty and cannot contain blank
  items.
- **Scores** are range-checked: overall scores 0–100, rubric scores 1–10.
- **`UsageRecord`** additionally enforces cross-field rules —
  `total_tokens == prompt_tokens + completion_tokens`, USD-only currency, and
  a reported cost whenever `cost_source == "reported"`.

The models are deliberately profession-neutral, store no protected
demographic information, and contain no hidden chain-of-thought field:
feedback is concise and structured, never a private monologue.

## Prompt-engineering library

`src/prompts.py` provides five system-prompt techniques — zero-shot,
role/persona, few-shot, structured analytical procedure, and
rubric-constrained structured output. All five target the *same* task and the
*same* `AnswerEvaluation` schema; only a technique-specific *method* block
changes, which is what makes the later prompt-comparison experiment fair. Each
prompt is assembled from shared blocks (mission, guardrails, session
parameters, task, method, output contract), and the output contract is
generated from `AnswerEvaluation.model_fields` so prompts cannot drift out of
sync with the models.

The trust boundary is enforced in message assembly: the **system** message
carries only repository-authored text plus fixed-vocabulary session settings,
while every free-text field the candidate supplies is placed in the **user**
message inside `<<<UNTRUSTED_REFERENCE_DATA>>>` delimiters. The shared
guardrails instruct the model to treat that content as data only, never follow
instructions embedded in it, never reveal the system prompt or hidden
reasoning, never fabricate achievements, label improved answers as examples to
personalise, stay profession-neutral, and avoid protected characteristics.

`src/prompt_registry.py` sits above the builders as a UI-facing catalogue:
`list_techniques()` and `selector_options()` drive the Streamlit selector,
`get_technique()` returns a technique's metadata and builder, and unknown IDs
raise a controlled `UnknownPromptTechniqueError` rather than crashing or
silently defaulting. See `docs/prompt_engineering.md` for each technique's
definition, benefits, risks, best use and expected effect.

## Security and privacy guards

`src/security.py` is a deterministic, **best-effort** defence layer (not
perfect or production-grade — the primary boundary is architectural). It
provides six controls that wrap the data flow:

- **Input validation** — `sanitize_text` removes null bytes, unsafe control
  and zero-width characters and collapses excessive whitespace; `validate_field`
  enforces named length limits and required-ness, rejecting oversized input
  rather than truncating it, with safe user-facing errors.
- **Injection detection** — `detect_injection` normalises text (defeating
  spacing/punctuation/leetspeak obfuscation) and scores it against multiple
  weighted indicators, returning one of three outcomes: `allow`,
  `allow_with_warning`, `block`.
- **Scope guard** — `check_scope` allows the full range of interview activities
  and blocks only clearly malicious, off-scope requests.
- **Untrusted-content wrappers** — `wrap_job_description`,
  `wrap_candidate_background` and `wrap_candidate_answer` frame content as
  data-only, reinforcing the message-separation boundary.
- **Output guard** — `inspect_output` checks JSON/schema validity, response
  size, system-prompt leakage markers and secret-like patterns.
- **Privacy notices** — `PRIVACY_NOTICES` provides UI-ready guidance.

See `docs/security.md` for the threat model, each control and the guard's
stated limitations.

## OpenRouter integration, usage and pricing

`src/openrouter_client.py` is a typed, **non-streaming** client for
`POST https://openrouter.ai/api/v1/chat/completions`. It:

- reads `OPENROUTER_API_KEY` securely via `AppConfig` (a masked `SecretStr`)
  and authenticates with a Bearer token;
- accepts `model`, `messages`, `temperature` and `max_tokens`, and attaches
  `response_format` only when the selected model supports it (otherwise it
  raises `UnsupportedParameterError` before any network call);
- uses explicit connection and read timeouts;
- returns a typed `ChatResult` (assistant content, actual model, prompt/
  completion/total tokens, reported cost, request duration, request ID);
- maps every failure to a specific exception — missing key, 400/401/402/429,
  5xx/upstream, timeout, network error, invalid JSON, empty choices — and
  degrades gracefully when usage is missing;
- logs nothing by default; a **safe debug mode** logs only request ID, model,
  duration and a coarse status category — never headers, keys or content;
- exposes `test_connection()`, a deliberately tiny request the UI runs only
  when the user presses a "Test connection" button.

`src/pricing_service.py` handles usage accounting and cost:

- prices are **read from OpenRouter model metadata** (`/models`) and cached for
  the session — never hard-coded;
- cost precedence is **reported** (from usage data) → **calculated** (from
  metadata, using `Decimal` for precision) → **unavailable**, and every
  `UsageRecord` records which source was used;
- all figures are in USD, and calculated figures are labelled estimates, not
  final billed amounts;
- `supported_parameters` from metadata drives the client's structured-output
  decision;
- cumulative session usage (tokens and cost) is tracked via
  `SessionUsageTotals`.

## Data flow

User input (job description, background, answers) → input guard (length and
injection checks) → message assembly (system prompt + conversation history
with correct role separation) → HTTPX request to OpenRouter → response
parsing (Pydantic validation for structured outputs) → rendering in
Streamlit → usage/cost accounting. All state lives in `st.session_state`
for the duration of the browser session only.

## Trust boundaries

- **Untrusted:** everything the user types — job descriptions, candidate
  backgrounds, interview answers. These are length-limited, screened, and
  always placed in *user* messages, never in system messages.
- **Trusted:** system prompts, constants and configuration authored in this
  repository.
- **Semi-trusted:** model responses — validated against Pydantic schemas
  before structured use; parsing failures are handled explicitly.
- **Secret:** the OpenRouter API key — held in Streamlit secrets or the
  environment, masked as a `SecretStr`, never rendered, logged or committed.

## State management

Streamlit reruns the script on every interaction, so all conversational
state (message history, settings, cumulative usage) is kept in
`st.session_state`. State is per-browser-session and in-memory only — no
database, no persistence, no candidate data retention.

## Security approach

- No default API key; controlled missing-configuration message.
- Input length limits and injection screening on all untrusted content.
- System prompt never exposed through the UI.
- No hidden chain-of-thought requests; structured rubrics with concise
  explanations instead.
- No fabrication of candidate achievements; no storage of protected
  demographic characteristics; no personality, health or psychological
  diagnoses; scores framed as practice feedback, never hiring decisions.
- Tests never call the live API.
- These controls are implemented deterministically in `src/security.py` and
  documented in `docs/security.md`; they are best-effort, not production-grade.

## Explicitly excluded scope

LangChain, LangGraph, RAG, embeddings, vector databases, autonomous agents,
databases, authentication, persistent candidate data, and production
deployment infrastructure are all out of scope for Sprint 1.

## Definition of done

- All 15 mandatory assignment outcomes demonstrably working.
- Targeted medium and hard optional tasks delivered.
- `pytest` passes with no live API calls; app starts cleanly with and
  without an API key configured.
- No secrets in the repository history.
- Documentation (README, architecture, learning notes, review prep)
  complete and consistent with the code.
