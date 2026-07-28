# CLAUDE.md — Interview Practice Studio

Guidance for AI-assisted development in this repository. All work must follow
these rules.

## Project scope

Turing College Sprint 1 project: **Foundations of LLM Application
Development — Build an Interview Practice App.**

Proposition: *"Prepare for any role. Practise realistically. Improve every
answer."*

The product is **generic across professions**. It must support candidates in
any domain (software, engineering, finance, sales, healthcare, legal, trades,
public sector, education, and more), at any career level, for any interview
type. No HR-specific assumptions may appear in core logic, prompts, scoring
or examples.

### In scope (Sprint 1)

- Streamlit interface with a full conversational chatbot (session state)
- OpenRouter Chat Completions integration via HTTPX
- Correct system / user / assistant message separation
- At least five system prompts using different prompting techniques
- At least one meaningful security guard
- Adjustable model settings; job-description context
- At least two structured JSON output types (Pydantic)
- Token and cost reporting
- Prompt-comparison experiment; jailbreak/invalid-input experiment → Excel
- Automated tests (pytest), documentation, project-review notes

### Explicitly excluded

LangChain, LangGraph, RAG, embeddings, vector databases, autonomous agents,
databases, authentication, persistent candidate data, production deployment
infrastructure.

## Stack and models

Python, Streamlit, OpenRouter Chat Completions API, Pydantic, HTTPX, Pytest,
Pandas, OpenPyXL.

Approved models only (defined centrally in `src/constants.py`):

- `openai/gpt-5-mini` — default
- `openai/gpt-5-nano` — lower cost
- `openai/gpt-5` — higher capability

## Architecture rules

- `app.py` renders the UI only. Business logic lives in `src/`.
- Constants (models, limits, defaults) live in `src/constants.py` only.
- Configuration is loaded via `src/config.py`: Streamlit secrets first,
  environment variable fallback, never a default key, controlled
  missing-configuration result — never a crash.
- Prefer explicit, readable Python over abstraction. A Sprint 1 learner must
  be able to understand every file.
- Type hints on all functions; docstrings on public functions and classes.

## Security constraints

- Never hard-code, print, log or commit an API key or any secret.
- Treat job descriptions, candidate backgrounds and answers as untrusted
  content; enforce input length limits from `src/constants.py`.
- Never expose the full system prompt through the UI.
- Never request hidden chain-of-thought; use structured evaluation
  procedures with concise explanations instead.
- Never fabricate candidate achievements, credentials, examples or metrics.
- Do not store protected demographic characteristics.
- Do not make personality, health or psychological diagnoses.
- Do not claim interview scores are objective hiring decisions — they are
  practice feedback only.

## Testing requirements

- Pytest for all automated tests; `tests/` mirrors `src/`.
- Never make live API calls in tests — mock HTTPX.
- Do not weaken tests to make them pass; do not silently swallow errors.

## Git rules

- Work directly on `main`; push to
  `moaltamimi-unbiasedtalent/Interview-Practice-Studio`.
- Commit and push only when a phase prompt instructs it.
- Never commit `.env`, `.streamlit/secrets.toml`, virtual environments,
  caches or generated local files.
- Do not modify files outside this repository.

## Academic explainability

The repository owner must be able to explain every line in a project review.
Therefore: keep code simple, comment the *why* where it is not obvious, and
maintain `docs/learning_notes.md` with concepts introduced, decisions made
and review questions after every phase. At the end of every implementation
phase, report files changed, functionality delivered, commands run, test
results, remaining risks, manual checks, review concepts, and git status.
