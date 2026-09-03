# Testing

No automated test makes a live/paid API call — everything is mocked or offline.

## Layers

| Layer | Where | Runs in CI |
|---|---|---|
| Unit + integration (Python) | `tests/` (pytest) | ✅ |
| End-to-end pipeline (mocked) | `tests/test_e2e_text.py` | ✅ |
| In-process UI journeys | `tests/test_app_smoke.py` (Streamlit `AppTest`) | ✅ |
| Frontend unit (state, metrics) | `components/live_interviewer/frontend` (vitest) | ✅ |
| Browser E2E | `e2e/` (Playwright) | ❌ local only (needs live server + browsers) |
| Manual live-API smoke | `scripts/manual_live_check.py` | ❌ manual, confirmation-gated |

## Run

```bash
# Python
python -m pytest -q

# Frontend
cd components/live_interviewer/frontend && npm install && npm test && npm run build

# Browser E2E (app must be running)
cd e2e && npm install && npm run install-browsers && BASE_URL=http://localhost:8501 npm test

# Manual live (chargeable — explicit confirmation required)
python scripts/manual_live_check.py                      # dry run
python scripts/manual_live_check.py --openrouter --confirm
```

## What the suite covers

- **Full interview pipeline** (strategy → question → answer → evaluation → Deep
  Dive → report) with authoritative-linkage and cost accounting.
- **Failure handling:** invalid key (401), insufficient credits (402), rate
  limit (429), provider 5xx, transient retry bounds, malformed/truncated
  structured responses, empty/unsupported/oversized audio, microphone/camera
  denied fallbacks, live-unavailable fallback, bounded reconnect.
- **Security:** prompt-injection blocking at the trust boundary, candidate
  answers treated as data, no untrusted data in component HTML, no secret/token
  in browser config, safe failure logging, and **cross-user isolation**.
- **Persistence:** round-trip, delete, delete-all, export, dashboard, and
  strict per-user scoping.
- **Delivery coaching:** timing maths, pause segmentation, aggregation (timing/
  pacing only — camera/visual coaching was withdrawn). An e2e test asserts the
  product never requests camera access.

## Experiments (offline, no live calls)

- `scripts/security_classifier_experiment.py` → `evaluations/security_classifier_experiment.*`
- `scripts/compare_prompts.py`, `scripts/compare_model_settings.py` (placeholders
  until run live with `--run --confirm`).
