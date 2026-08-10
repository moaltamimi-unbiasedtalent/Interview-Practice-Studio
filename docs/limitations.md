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
