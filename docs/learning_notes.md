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
