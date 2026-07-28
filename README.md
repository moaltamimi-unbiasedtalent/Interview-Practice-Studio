# Interview Practice Studio

**Prepare for any role. Practise realistically. Improve every answer.**

An LLM-powered interview practice app for candidates in **any profession** —
software, engineering, finance, sales, healthcare, legal, trades, public
sector, education and beyond — at any career level and for any interview
type. Built with Python, Streamlit and the OpenRouter Chat Completions API
as a Turing College Sprint 1 project.

> **Status: Phase 1 — foundation.** The app currently displays the product
> shell and configuration status. It makes no API requests yet. Interview
> practice features arrive in later phases.

## Requirements

- Python 3.10+
- An [OpenRouter](https://openrouter.ai) API key (for later phases)

## Setup

```bash
git clone https://github.com/moaltamimi-unbiasedtalent/Interview-Practice-Studio.git
cd Interview-Practice-Studio

python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Configure the API key

Preferred — Streamlit secrets:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# edit .streamlit/secrets.toml and add your key
```

Local development fallback — environment variable:

```bash
cp .env.example .env
# edit .env and add your key
```

`.streamlit/secrets.toml` and `.env` are gitignored. **Never commit a key.**
The app never uses a default key and shows a controlled message when no key
is configured.

## Run

```bash
streamlit run app.py
```

## Test

```bash
pytest
```

Tests never make live API calls.

## Project structure

```
app.py                  Streamlit UI (rendering only)
src/                    Business logic
  config.py             Configuration loading (secrets → env fallback)
  constants.py          Approved models, safe defaults, input limits
tests/                  Pytest suite (no live API calls)
docs/                   Architecture and learning notes
.streamlit/             Streamlit config + secrets example
CLAUDE.md               Development rules for AI-assisted work
```

## Approved models

| Model | Role |
| --- | --- |
| `openai/gpt-5-mini` | Default |
| `openai/gpt-5-nano` | Lower cost |
| `openai/gpt-5` | Higher capability |

## A note on feedback

Interview scores and feedback produced by this app are **practice guidance
only** — not objective hiring decisions, and not assessments of personality
or psychology.
