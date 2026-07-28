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
┌─────────────────────────────────────────────┐
│ app.py — Streamlit UI (rendering only)      │
│  session state: conversation, settings      │
└──────────────┬──────────────────────────────┘
               │ calls
┌──────────────▼──────────────────────────────┐
│ src/ — business logic                       │
│  config.py     configuration loading        │
│  constants.py  models, limits, defaults     │
│  (later phases:)                            │
│  client.py     OpenRouter via HTTPX         │
│  prompts.py    system prompt library        │
│  guard.py      input security guard         │
│  schemas.py    structured JSON outputs      │
│  pricing.py    token/cost reporting         │
└──────────────┬──────────────────────────────┘
               │ HTTPS (HTTPX)
┌──────────────▼──────────────────────────────┐
│ OpenRouter Chat Completions API             │
│  openai/gpt-5-mini | gpt-5-nano | gpt-5     │
└─────────────────────────────────────────────┘
```

## Main components

- **`app.py`** — Streamlit rendering only; no business logic.
- **`src/config.py`** — resolves the API key (Streamlit secrets first,
  environment fallback); returns a controlled result when missing.
- **`src/constants.py`** — the single source of truth for approved models,
  generation defaults and input length limits.
- **Later phases** — OpenRouter client, prompt library, security guard,
  structured output schemas, pricing/usage reporting, experiments.

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
