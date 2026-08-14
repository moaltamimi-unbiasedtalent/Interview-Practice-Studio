# Limitations — Interview Practice Studio

An honest, plain-language list of what this Sprint 1 application does **not**
guarantee. These are stated openly so reviewers and users understand the
boundaries of the tool.

## Feedback quality

- **LLM feedback may be inaccurate or inconsistent.** The model can misjudge an
  answer, vary between runs, or miss nuance. Treat every score and comment as a
  prompt for reflection, not a verdict.
- **Interview scores are advisory.** They are practice guidance, not objective
  hiring decisions and not assessments of personality, health or psychology.
- **No guarantee of success.** The app does not promise employment, or that you
  will pass any real interview.

## Security

- **Prompt-injection defences are best-effort.** The deterministic guard is
  pattern-based, not a model, and does not stop every possible jailbreak.
- **Encoding bypasses remain possible.** Only a narrow, high-confidence Base64
  case is decoded and re-scanned; other encodings (URL/hex/ROT13), nested or
  whitespace-split Base64, and novel obfuscations may bypass local detection.
  The primary defence is architectural: untrusted text is framed as data in the
  prompt.
- **False positives remain possible.** Pattern-based detection can occasionally
  flag benign text; benign and legitimate-technical cases are tested to keep
  this low, but it cannot be eliminated.

## Cost and provider

- **Model availability and prices can change.** OpenRouter model metadata and
  pricing are read live and may change over time.
- **Estimated cost is not the final bill.** When OpenRouter does not report a
  cost, the app shows a calculated estimate in USD; it is labelled as an
  estimate, not the amount you will be billed.
- **Your content is processed externally.** Interview content is sent through
  OpenRouter to the selected model provider.
- **Do not paste confidential or unnecessary sensitive information.** Provide
  only what you are comfortable sending to a third-party model.

## Data and accounts

- **No intentional persistence.** Interview content lives in the Streamlit
  session (in memory) for the duration of the browser session only; the app
  does not deliberately write interview content to disk or a database.
- **No authentication or user database.** There is no login, and no per-user
  storage.

## Testing and accessibility

- **Accessibility needs manual validation.** Automated tests check structure,
  but heading hierarchy, colour-independent cues, keyboard navigation and
  screen-reader behaviour still require manual browser/screen-reader checks.
- **Mocked tests cannot fully verify live provider behaviour.** The automated
  suite mocks all network calls, so it verifies request construction and
  handling, not the model's real responses. Live behaviour is only exercised
  through the explicitly gated experiment paths.

## Interview Deep Dive (branching)

- **Bounded by design.** A deep dive allows at most two deeper levels
  (`MAX_BRANCH_DEPTH`) before you must return to the main interview. This is
  deliberate — it prevents runaway token usage, confusing navigation and
  uncontrolled state; it is not an open-ended conversation or an agent.
- **Extra cost.** Each deep-dive question and its evaluation are additional
  model calls, so exploring adds to session usage and cost.
- **Interview-focused only.** Branch answers are treated as untrusted data, so
  a deep dive cannot be used to turn the app into a general-purpose assistant;
  the same best-effort security limits apply as elsewhere.

## Scope (Sprint 1)

- **No RAG or vector search.** There is no retrieval-augmented generation,
  embeddings or vector database. Also excluded: LangChain, LangGraph, autonomous
  agents and persistent databases. These are candidates for Sprint 2.

---

## Product hardening (Phase 15)

- **Strict schema depends on the provider.** Strict JSON Schema output is used
  only when the selected model advertises `structured_outputs`; the request asks
  OpenRouter to route to a provider that can enforce it. If none can, the request
  surfaces a controlled error rather than silently degrading. Models without
  enforcement use the defensive parser with one repair.
- **Bounded transient retry.** Exactly one HTTP-level retry for transient errors
  (network/timeout/429/502/503); everything else fails immediately. One user
  action makes at most 3 generation requests (strict → defensive fallback), each
  with at most one transient retry.
- **Capabilities are metadata-driven.** Parameter support (e.g. temperature) is
  read from OpenRouter metadata; a model that does not support a setting hides it
  in the UI. Metadata is fetched lazily and cached per session.
- **Reasoning-effort sweep not yet parameterised.** The model-settings experiment
  compares the output-token budget (always supported) and temperature only when
  supported; sweeping reasoning effort would require threading it through
  `ModelSettings` and is deferred.

---

## Voice answers (Phase 16)

- **Provider dependence.** Voice requires a configured Google Cloud project and
  Application Default Credentials. Without them, voice shows an unavailable state
  and typing still works.
- **Transcription cost is not priced.** Audio-second usage is recorded, but no
  dollar cost is displayed unless a real rate is configured (pricing is never
  invented).
- **Duration checks are WAV-based.** The 10-minute cap is enforced from the WAV
  header; non-WAV formats are bounded by the byte-size cap instead.
- **Recorded-only.** This phase uses Streamlit's native audio input (record then
  transcribe). Real-time streaming (Gemini Live) is not implemented.
- **Voice metrics captured, not scored.** Duration/word-count/WPM are stored for
  the later timing/coaching phase.

---

## Live interview (Phase 17, experimental)

- **Experimental and optional.** Requires a Gemini key and a built frontend
  component; otherwise the mode shows a fallback and Voice/Text still work.
- **Frontend not built or exercised in CI.** The TypeScript component is shipped
  as source; it is not built or run in automated tests, and no live Gemini call
  is made in CI. Only the Python backend and the graceful-fallback path are
  covered by the automated suite; browser behaviour is covered by the manual QA
  plan (`docs/live_interview_qa.md`).
- **Gemini cost is not priced.** Session usage is tracked separately from LLM
  cost; no dollar figure is shown unless a real rate is configured.
- **Single engine preserved.** Gemini never authors questions or changes
  progression; it only voices the canonical OpenRouter question and may make
  brief acknowledgements.
