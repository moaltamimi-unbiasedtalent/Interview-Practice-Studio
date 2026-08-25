# Product Readiness Report — Interview Practice Studio

Phase 22 (final integration). Prepared on the `product/full-fledged-interview-app`
branch. This is a candid assessment: what is proven, what is scaffolded, and
what must be completed before production.

## Headline

- **Text Practice is complete and works end to end**, backed by an automated
  full-pipeline test and the whole unit/integration suite.
- **Voice (Speech-to-Text) and Live (Gemini) are fully wired in code but ship as
  placeholders** pending real credentials and live verification, which are to be
  completed during the capstone. Without their keys the app runs on Text and
  shows graceful fallbacks for the other two — no crashes, no lost progress.

## Completed capabilities

- Profession-neutral interview engine (OpenRouter): strategy, questions,
  evaluation, Deep Dive (bounded depth), final report.
- Structured outputs with provider-enforced JSON Schema where available, plus a
  defensive parser + one repair for models without it.
- Recorded-voice mode: transcription (short = sync, long = streaming), editable
  transcript, delivery/pacing coaching.
- Live mode: ephemeral-token backend, package-based browser component (built),
  turn state machine, bounded reconnect, graceful fallback.
- Optional Visual Engagement Coach (local-only, opt-in, coaching-only).
- Delivery & pacing coach; accounts, persistent history, dashboard/progress,
  export & delete.

## Architecture (one engine)

OpenRouter is the sole interview intelligence. Speech and Gemini are I/O
interfaces only; Gemini never authors or alters canonical questions. UI renders
only; business logic lives in `src/`; persistence goes through a user-scoped
repository. See `docs/architecture.md`.

## Test evidence (no live calls)

| Suite | Result |
|---|---|
| Python (pytest) | **691 passed, 1 skipped** |
| Full interview pipeline E2E (mocked) | ✅ `tests/test_e2e_text.py` |
| In-process UI journeys (AppTest) | ✅ `tests/test_app_smoke.py` |
| Frontend (vitest) | **10 passed** |
| Compile | ✅ |
| Secret scan (source) | ✅ clean |
| Browser E2E (Playwright) | scaffolded (`e2e/`), local-only |

Failure handling covered by tests: invalid key (401), insufficient credits
(402), rate limit (429), provider 5xx + bounded transient retry, malformed/
truncated structured output, empty/unsupported/oversized audio, mic/camera
denied fallbacks, live-unavailable fallback, cross-user isolation.

## Live-test evidence

Not yet run — requires credentials (capstone). Use `scripts/manual_live_check.py`
(confirmation-gated) to record OpenRouter / Speech / Gemini outcomes without
exposing credentials.

## Privacy & security

- No raw video/audio stored; camera processing is local; only aggregated metrics
  persist. Transcripts persist only per account/session; deletion truly deletes.
- Prompt-injection blocked at the trust boundary; candidate answers treated as
  data; no untrusted data interpolated into component HTML; safe-metadata-only
  logging; permanent keys backend-only (browser gets ephemeral tokens).
- Security classifier experiment (`evaluations/security_classifier_experiment.*`)
  found the deterministic guard already catches the obvious attacks (0 false
  negatives on the set) → **retain deterministic; defer a moderation-API
  classifier** pending a live cost/latency evaluation. See `docs/security.md`,
  `docs/privacy.md`.

## Performance (targets)

Network-dependent latency must be measured live (manual suite). Proposed product
targets to verify: strategy < 8 s; question < 6 s; evaluation < 8 s;
transcription < 1× audio length; live first response < 2 s; reconnect < 5 s;
final report < 12 s. The offline pipeline overhead (parse/validate/route) is
sub-millisecond and not the bottleneck.

## Cost

Figures are **not invented**: real per-question/per-session costs come from
OpenRouter usage metadata (already recorded per request) and Gemini/Speech
usage, captured during live sessions via the manual suite. The app displays LLM
and transcription cost separately and never claims a figure without metadata.

## Accessibility

Captions toggle; avatar `role="img"` + `aria-label`; `prefers-reduced-motion`
respected; markdown auto-escaped (no `unsafe_allow_html`). Full keyboard/screen-
reader/contrast/zoom review should be completed in a real browser session.

## Known limitations

- Voice/Live are placeholders pending credentials + live verification (capstone).
- `gemini-3.1-flash-live-preview` is an unverified model id (overridable via
  `GEMINI_LIVE_MODEL`); confirm against the live API.
- Browser E2E and live/manual suites are not part of CI.
- Long-audio streaming path is tested with fakes; verify against real Speech V2.

## Production blockers

1. Provide and verify OpenRouter, Google Speech (project + ADC + billing) and
   Gemini credentials.
2. Run the manual live suite and record real latency/cost.
3. Apply Alembic migrations against the production PostgreSQL.
4. Configure OIDC `[auth]` and set `APP_AUTH_REQUIRED=true`.

## Recommendations

- Ship Text Practice now; gate Voice/Live behind their credentials (already the
  behaviour).
- Complete Voice/Live live verification during the capstone, then re-run this
  report's live-evidence, performance and cost sections with real numbers.
