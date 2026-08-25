# Browser E2E (Playwright)

Full-browser journeys for the candidate experience. These run **locally against
a running app**, not in CI (Streamlit needs a live server and installed
browsers). Paid provider calls are avoided — the specs exercise the landing,
mode cards, setup form and the Voice/Live fallbacks.

The in-process UI journeys (fast, mocked, run in CI) live in
`tests/test_app_smoke.py` via Streamlit's `AppTest`; Playwright complements them
with real-browser coverage.

## Run

```bash
# 1. Start the app in one terminal
cd .. && python -m streamlit run app.py

# 2. In another terminal
cd e2e
npm install
npm run install-browsers
BASE_URL=http://localhost:8501 npm test
```

To exercise a full Text interview that calls OpenRouter, set a key in
`.streamlit/secrets.toml` first and extend the spec — keep paid flows out of any
automated CI run.
