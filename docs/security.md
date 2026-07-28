# Security and privacy — Interview Practice Studio

This document describes the deterministic guards in `src/security.py` and how
they fit the trust boundaries in `docs/architecture.md`.

> **Important limitation.** These guards are a **best-effort, deterministic**
> layer for a Sprint 1 learning project — regexes, weighted indicators and
> length checks. They are **not perfect and not production-grade**. They cannot
> catch every prompt-injection or misuse attempt, and they can occasionally
> flag benign text. They reduce obvious risk; they do not eliminate it. The
> primary defence is architectural: untrusted content stays in the user message
> and is wrapped as data (see `src/prompts.py`).

## Threat model (Sprint 1)

- **Untrusted input.** Job descriptions, candidate backgrounds, answers and
  other free text may contain junk, oversized payloads, control characters or
  prompt-injection attempts.
- **Prompt injection.** Text that tries to override the system prompt, reveal
  it, change the model's role, or exfiltrate secrets — directly or obfuscated.
- **Off-scope misuse.** Attempts to turn the interview coach into a
  general-purpose or malicious assistant.
- **Model output risks.** Malformed structured output, system-prompt leakage,
  or secret-like content in responses.

Out of scope: authentication, network security, persistence security (there is
no database), and defending against a determined adversary.

## Controls

### A. Input validation and normalisation

`sanitize_text` removes null bytes and unsafe C0/C1 control characters, strips
zero-width and bidirectional-override characters, normalises line endings, and
collapses excessive whitespace — **without changing meaning**. `validate_field`
then applies a named `FieldSpec` per field (`target_role`, `industry`,
`company_context`, `job_description`, `candidate_background`,
`candidate_answer`, `instructions`):

- rejects empty **required** fields;
- enforces a named maximum length from `src/constants.py`;
- **rejects oversized input rather than truncating it**, so the user is never
  silently altered;
- raises `InputValidationError` with a short, safe, user-facing message that
  never echoes the payload.

### B. Prompt-injection risk detection

`detect_injection` normalises text for detection (NFKC, lowercase, leetspeak
mapping, then stripping to alphanumerics) so that spacing, punctuation and
digit-substitution obfuscation (`i g n o r e`, `i.g.n.o.r.e`, `1gn0re`) all
collapse to the same form. It then scores the text against **multiple weighted
indicators** — not exact phrases — covering: ignore/disregard/forget
instructions, reveal/print the system prompt, change your role, act as an
unrestricted/jailbreak persona, expose API keys or environment variables,
bypass/disable security, execute shell commands, and treating embedded content
as system instructions.

The summed score maps to **three outcomes** using thresholds in
`src/constants.py`:

| Score | Outcome |
|------|---------|
| `>= INJECTION_BLOCK_SCORE` (4) | `block` |
| `>= INJECTION_WARN_SCORE` (2) | `allow_with_warning` |
| otherwise | `allow` |

A single strong indicator (weight 4) blocks on its own; milder signals
accumulate. The result lists which indicators fired so the UI can explain a
warning or block. Indicators are phrase-shaped (e.g. `system` next to `prompt`),
so ordinary technical words like *system*, *execute* and *administrator* do not
trip the guard.

### C. Scope guard

`check_scope` **defaults to allow**, because legitimate interview practice is
broad: role and job-description analysis, question generation,
behavioural/technical/functional/leadership/case practice, answer feedback,
questions for the interviewer, and appropriate salary-negotiation practice. It
blocks only requests matching a **clearly malicious, off-scope** intent:
credential theft, secret extraction, malware creation, destructive command
execution, or turning the app into an unrestricted assistant. Talking *about*
security work (e.g. interviewing for a security role) is allowed.

### D. Untrusted-content wrappers

`wrap_job_description`, `wrap_candidate_background` and `wrap_candidate_answer`
(built on `wrap_untrusted`) frame content in a delimited, data-only block with
a header stating that the content is untrusted reference data and that any
instructions inside it must not be followed. The wrappers do not sanitise
content — they frame it — so they complement, not replace, input validation.

### E. Output guard

`inspect_output` checks a model response before it is used or shown:

- **content type / JSON** — when JSON is expected, it must parse and
  (optionally) validate against the given Pydantic schema (e.g.
  `AnswerEvaluation`);
- **size** — responses above `MAX_MODEL_OUTPUT_CHARS` are rejected;
- **system-prompt leakage** — known markers from our own prompts (e.g.
  "OPERATING RULES", the untrusted-data delimiters) are flagged;
- **secret-like patterns** — OpenAI/OpenRouter/GitHub/AWS key shapes, private
  key headers and bearer tokens are flagged.

Any issue yields `block` with a list of reasons; otherwise `allow` (and the
parsed JSON when applicable).

### F. Privacy notices

`PRIVACY_NOTICES` / `privacy_notices()` provide UI-ready statements:

- Do not paste confidential or proprietary company information.
- Do not provide unnecessary sensitive personal information.
- Content is sent through OpenRouter to the selected model.
- The Sprint 1 app does not intentionally persist interview content after the
  session.
- Feedback and scores are practice guidance, not an objective employment
  decision.

## How the layers combine

1. **Validate** every free-text field on input (reject empty/oversized, clean
   control characters).
2. **Screen** untrusted reference fields with `detect_injection`; block or warn.
3. **Scope-check** user requests/instructions with `check_scope`.
4. **Wrap** untrusted content as data before it reaches the model.
5. **Inspect** the model's response before displaying or parsing it.

No single layer is sufficient; together they raise the cost of obvious misuse
while keeping the app usable across every profession.
