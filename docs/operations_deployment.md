# Operations & Deployment

## Configuration

All configuration is via environment variables or `.streamlit/secrets.toml`
(secrets take precedence). **No secret is ever baked into the image or committed.**

| Setting | Purpose | Default |
|---|---|---|
| `OPENROUTER_API_KEY` | Core interview engine (required) | — |
| `APP_AUTH_REQUIRED` | Require OIDC login (production) | `false` |
| `DATABASE_URL` | SQLite (dev) / PostgreSQL (prod) | `sqlite:///data/interview_studio.db` |
| `GOOGLE_SPEECH_PROJECT_ID` | Enables Voice (Speech-to-Text) | — |
| `GOOGLE_SPEECH_LOCATION` | Speech region | `global` |
| `GOOGLE_APPLICATION_CREDENTIALS` | ADC for Speech | — |
| `GEMINI_API_KEY` | Enables Live (backend-only; mints ephemeral tokens) | — |
| `GEMINI_LIVE_MODEL` | Live model id | `gemini-3.1-flash-live-preview` |
| `[auth]` (secrets.toml) | Streamlit OIDC provider config | — |

> **Capstone note:** Voice (Speech-to-Text) and Live (Gemini) are wired end to
> end in code but ship as **placeholders pending credentials** — they are to be
> completed and verified live during the capstone. Without their keys the app
> runs fully on **Text Practice** and shows graceful fallbacks for the other two.

## Startup validation & health

- `src/health.py` provides `startup_validation(config)` (hard errors vs. soft
  info) and `health_check(config, database_ok=...)`.
- Streamlit's built-in probe `GET /_stcore/health` is used by the Docker
  `HEALTHCHECK`. For a richer readiness signal, surface `health_check(...)`.

## Database & migrations

**Migration ownership.** Local development and tests (SQLite) create tables with
`init_db` → `create_all`. **Production (any non-SQLite database) is schema-owned by
Alembic** — `init_db` no longer calls `create_all` there, so the schema is never
silently created or altered at startup; run migrations explicitly. The baseline
revision `0001_initial` is **immutable**: it uses explicit `op.create_table` /
`op.create_index` operations (it does not import the live model metadata), so a
later model change cannot retroactively alter it. Add schema changes as new
revisions (`alembic revision --autogenerate`), never by editing `0001`.

- Dev/tests: `init_db` creates the SQLite schema automatically.
- Production applies Alembic migrations:
  ```bash
  pip install -e ".[db]"
  DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db alembic upgrade head
  ```

## Docker

```bash
docker build -t interview-os-coach .
docker run --rm -p 8501:8501 \
  -e OPENROUTER_API_KEY=... \
  -e DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db \
  -e APP_AUTH_REQUIRED=true \
  interview-os-coach
```

Secrets are provided at **runtime** (env or mounted file) — never in the image
(enforced by `.dockerignore`, which excludes `.streamlit/secrets.toml`, `.env`,
`data/`, tests and node_modules). The Live frontend component is not built into
the image by default (Live falls back); build and mount it to enable Live.

## CI

`.github/workflows/ci.yml` runs on push/PR:
- **Python:** compile, `pytest` (no live calls), and a secret scan that fails on
  real-looking keys in source.
- **Frontend:** `npm install`, vitest, typecheck, `vite build`.

Browser E2E (Playwright, `e2e/`) is **not** in CI — it needs a live server and
browsers; run it locally (see `e2e/README.md`).

## Secrets handling

- Store provider keys only in `.streamlit/secrets.toml` (gitignored) or the
  environment. Never paste keys into chat, logs, or commits.
- The permanent Gemini key stays backend-only; the browser receives only a
  short-lived ephemeral token.
- Google Speech uses Application Default Credentials; the service-account JSON is
  referenced by path and never committed.
