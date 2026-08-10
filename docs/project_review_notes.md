# Project review notes — Interview Practice Studio

Preparation for the Turing College review. Everything here is grounded in the
actual code, tests and evaluation files. Rehearse the explanations in your own
words; the file/component pointers tell you where to look to verify each claim.

---

## Part 1 — Prepared explanations

### 1. Two-minute project introduction

Interview Practice Studio helps candidates in **any profession** practise
interviews and improve their answers. You set up a role (optionally pasting a
job description), the app generates a preparation **strategy**, then runs a
multi-turn mock interview: one question at a time, a rubric-based evaluation of
each answer, an improved example to personalise, and a follow-up. It finishes
with a downloadable readiness report. It integrates OpenRouter, offers five
prompt-engineering techniques and three models, reports token cost in USD, and
has a deterministic security guard with an exported jailbreak evaluation. Scores
are practice guidance, never hiring decisions.

### 2. Five-minute architecture walkthrough

`app.py` is a thin Streamlit UI that only renders and routes on the session
state. All logic is in `src/`:
- **Domain models** (`models.py`) — validated Pydantic schemas.
- **Prompts** (`prompts.py`, `prompt_registry.py`) — five techniques and
  task-aware message assembly.
- **Security** (`security.py`) — validation, injection scoring, scope, output
  checks.
- **Client** (`openrouter_client.py`) — typed OpenRouter calls.
- **Pricing** (`pricing_service.py`) — usage and cost.
- **Parser** (`response_parser.py`) — safe JSON + one repair.
- **Services** (`interview_service.py`, `evaluation_service.py`,
  `report_service.py`) — the four use cases, dependency-injected.
- **Session** (`session_manager.py`) — the interview state machine.
Walk the data flow: UI → validate/screen (security) → build role-separated
messages (prompts) → client → parse+validate (parser/models) → account cost
(pricing) → render. See `docs/architecture.md`.

### 3. Application workflow

`SETUP → STRATEGY_READY → AWAITING_ANSWER → EVALUATING → INTERVIEW_IN_PROGRESS`
(loop) `→ INTERVIEW_COMPLETE → REPORT_READY`, with `ERROR` recoverable. Each
transition is guarded by `session_manager.py`.

### 4. System, user and assistant roles

The **system** message carries only trusted, repository-authored instructions
plus fixed-vocabulary session parameters. The **user** message carries all
free-text the candidate typed (role, sector, JD, background, question, answer),
wrapped as untrusted data. **Assistant** messages are the model's replies.
Inspect `src/prompts.py::build_task_messages`.

### 5. Each prompt technique

Zero-shot (direct), role/persona (adopt an interviewer viewpoint), few-shot (one
worked weak→evaluation→improved example), structured analytical procedure (a
visible six-step method, returning only the final output), and rubric-
constrained structured output (explicit criteria + strict JSON). All target the
same `AnswerEvaluation`. Inspect `src/prompts.py`, `docs/prompt_engineering.md`.

### 6. Temperature

Controls randomness of sampling. Lower (e.g. 0.1) is more focused/repeatable;
higher (0.9) is more varied. It is a session setting, bounded in
`src/constants.py`, and only sent when the model supports it.

### 7. Max tokens

Caps the length of the model's output (not the input). Bounded in
`src/constants.py`; used to trade completeness against cost/latency (the
"concise vs detailed" model-setting experiment).

### 8. Model selection

Three approved models (`openai/gpt-5-mini` default, `gpt-5-nano` cheaper,
`gpt-5` higher capability) in `src/constants.py::APPROVED_MODELS`. The UI only
offers these; `ModelSettings` validates the choice.

### 9. Structured JSON

The model is asked to return a single JSON object matching a schema. This makes
output machine-checkable and comparable across techniques. Inspect the OUTPUT
CONTRACT in `src/prompts.py` and the schemas in `src/models.py`.

### 10. Pydantic

Pydantic v2 validates the JSON into typed objects: it strips whitespace, rejects
empty/oversized fields, enforces enum-like values against `constants.py`, and
range-checks scores. Invalid output is rejected, never silently accepted.
Inspect `src/models.py`.

### 11. Streamlit session state

Streamlit re-runs the whole script on every interaction. `session_manager.py`
keeps all interview data under one namespaced key so it survives reruns, and
never stores button state as truth. Inspect `src/session_manager.py`.

### 12. Prompt injection

Untrusted text trying to change model behaviour (ignore instructions, reveal the
system prompt, exfiltrate secrets, change role). Direct = aimed at the assistant;
indirect = hidden in content like a job description. Guard: `src/security.py`.

### 13. Secret management

The key is read from Streamlit secrets first, then an env var; never a default.
It is stored as a Pydantic `SecretStr` (masked) and never logged. Inspect
`src/config.py`, `src/openrouter_client.py`. `.streamlit/secrets.toml` and
`.env` are gitignored and untracked.

### 14. Usage and cost

`pricing_service.py` reads live model pricing (cached per session) and resolves
cost as reported → calculated → unavailable, in USD; cumulative session cost is
tracked without double-counting on reruns. Inspect `src/pricing_service.py`,
`src/session_manager.py::record_usage`.

### 15. Deterministic vs live-model tests

Automated tests are deterministic and mock all network calls (fake clients,
injected fetchers), so they verify request construction and handling without
cost or flakiness. Live behaviour is only exercised via explicitly gated,
chargeable experiment paths.

### 16. Known limitations

Best-effort guard; advisory scores; estimated (not billed) cost; external
processing; no persistence/auth; no RAG/vectors/agents in Sprint 1. See
`docs/limitations.md`.

### 17. How Sprint 2 could introduce RAG

Index the candidate's CV and the job description into a vector store, retrieve
the most relevant chunks per question, and add them (still as untrusted data) to
the user message — improving role specificity without changing the guard or the
schemas.

### 18. Why LangChain was not used in Sprint 1

The scope forbids it, and the app is simple enough that a thin typed HTTPX
client plus Pydantic is clearer, easier to test, and easier to explain than a
framework. Fewer dependencies, no hidden control flow.

### 19. Why scores are advisory

They are one model's opinion on one answer, variable between runs and imperfect.
They are framed everywhere as practice guidance, never an objective or hiring
measure — see the UI captions and `docs/limitations.md`.

### 20. How duplicate OpenRouter calls are prevented

Two layers: the state machine only allows an action from the correct state (a
re-submitted answer hits `EVALUATING` and is rejected), and `begin_operation`/
`end_operation` claim an in-flight slot so a Streamlit rerun cannot fire a second
call. Cost is recorded once per completed operation. Inspect
`src/session_manager.py`, `app.py`.

---

## Part 2 — Reviewer questions (with answers, evidence and a follow-up)

> Answers are concise on purpose; expand them in your own words. "Inspect"
> points to where the behaviour is defined.

1. **Is this just a wrapper around an LLM?**
   No — it adds validated schemas, a five-technique prompt system, a security
   guard, cost accounting, a state machine and reproducible experiments.
   *Inspect:* `src/` overall. *Follow-up:* which part is most non-trivial?

2. **Why separate `app.py` from services?**
   So logic is testable without Streamlit and the UI stays a thin renderer.
   *Inspect:* `app.py` vs `src/*_service.py`. *Follow-up:* how do you test a
   service without a browser?

3. **Why use Pydantic?**
   To validate untrusted model output into typed objects and reject malformed
   data. *Inspect:* `src/models.py`. *Follow-up:* what happens on an invalid
   score?

4. **Why a prompt registry?**
   A stable ID → technique/metadata catalogue the UI and experiments share, with
   safe rejection of unknown IDs. *Inspect:* `src/prompt_registry.py`.
   *Follow-up:* what happens if an unknown technique ID is requested?

5. **Why not put the API key in `.env` only?**
   Streamlit deployments use `secrets.toml`; `.env` is a local fallback. Both
   gitignored, never a default key. *Inspect:* `src/config.py`. *Follow-up:*
   what does the app do with no key?

6. **Can the prompt guard be bypassed?**
   Yes — it is best-effort pattern matching; novel encodings/obfuscations can
   slip through. The architectural data-framing defence is primary. *Inspect:*
   `src/security.py`, `docs/security.md`. *Follow-up:* give an example it would
   miss.

7. **Why was Base64 decoding added?**
   To close the Phase-10 JB-22 gap: a bounded, high-confidence Base64 segment is
   decoded and re-scanned by the same scanner. *Inspect:*
   `security.py::_decode_high_confidence_base64`. *Follow-up:* why not decode
   everything?

8. **What prevents arbitrary encoded content from being decoded?**
   Strict limits: standalone tokens length 20–256, valid padding, printable
   UTF-8, ≤5 segments/1000 chars, and only re-scanned (never executed).
   *Inspect:* same function + `tests/test_security.py::TestBase64Injection`.
   *Follow-up:* what false positive did you test against?

9. **What happens after malformed JSON?**
   The parser strips fences, tries `json.loads`, validates; on failure it makes
   one repair attempt, then returns a controlled error. *Inspect:*
   `src/response_parser.py`. *Follow-up:* why not retry forever?

10. **Why only one repair attempt?**
    To bound cost and latency and avoid loops; a second failure is surfaced as a
    controlled `ModelResponseError`. *Inspect:* `response_parser.py`,
    `interview_service.py`. *Follow-up:* how is the repair prompt built?

11. **How do reruns cause duplicate API calls?**
    Streamlit re-executes the script on every interaction, so naive code could
    re-fire the same call. *Inspect:* `app.py` handlers. *Follow-up:* how did you
    stop it?

12. **How did you prevent duplicate costs?**
    `begin_operation` guard + state transitions ensure one call per action, and
    usage is recorded once per completed operation. *Inspect:*
    `session_manager.py`. *Follow-up:* show the test.

13. **How did you compare prompts fairly?**
    Same scenario, model, temperature, token limit and schema; only the
    technique changes. *Inspect:* `scripts/compare_prompts.py`. *Follow-up:*
    what would make it unfair?

14. **What evidence supports your chosen prompt technique?**
    Honestly: the recorded comparison run did not capture usable metrics (all
    calls errored), so no data-backed winner is claimed yet; the default is
    `rubric_json` for reliable JSON. *Inspect:* `evaluations/prompt_comparison.*`,
    `docs/prompt_engineering.md`. *Follow-up:* how would you gather that
    evidence?

15. **Why does a lower temperature not guarantee identical output?**
    Even at low temperature sampling is not fully deterministic, and provider
    conditions vary; lower only reduces variance. *Follow-up:* what would you
    fix to compare runs?

16. **What happens when OpenRouter returns 429?**
    The client raises `RateLimitError`, mapped to a controlled domain error with
    a clear message; no stack trace or secret. *Inspect:*
    `openrouter_client.py`, `tests/test_openrouter_client.py`. *Follow-up:* what
    other statuses are mapped?

17. **How does the app behave without a job description?**
    It is optional; the strategy and questions still work from the role/sector.
    *Inspect:* `tests/test_interview_service.py::test_works_without_job_description`.
    *Follow-up:* how does the JD change the prompt when present?

18. **How does it stay generic across professions?**
    The system prompt is neutral ("every profession"); the role travels in the
    user message. *Inspect:* `tests/test_generic_professions.py`. *Follow-up:*
    show it for a nurse and a CEO.

19. **Why is the final score not an objective measure?**
    It is one model's variable judgement of one answer; the app labels it
    practice guidance everywhere. *Inspect:* UI captions, `docs/limitations.md`.
    *Follow-up:* how would you validate scoring quality?

20. **What would you change before production?**
    Auth + consented persistence, live-model regression tests, accessibility
    validation, rate-limit backoff, and broader encoding defences. *Follow-up:*
    which is highest priority and why?

21. **Where is the system prompt, and is it ever shown to the user?**
    Built in `src/prompts.py`; never rendered — the guard also scans output for
    leakage. *Inspect:* `security.py::inspect_output`. *Follow-up:* how do you
    detect a leak?

22. **How are candidate answers protected if they contain an injection?**
    They are framed as untrusted data and evaluated anyway (warned, not blocked)
    — blocking a real answer would break the core use case. *Inspect:*
    `run_jailbreak_tests.py` JB-29, `docs/security.md`. *Follow-up:* why warn
    instead of block here?

23. **Why is `response_format` only sometimes sent?**
    Only when the model's metadata reports support; otherwise the prompt-only
    JSON contract applies. *Inspect:* services + `pricing_service.supported_parameters`.
    *Follow-up:* what did the metadata say for gpt-5-mini?

24. **What are the explicit timeouts and why?**
    A short connect timeout fails fast; a longer read timeout tolerates slow
    generations. *Inspect:* `config.py`, `openrouter_client.py`. *Follow-up:*
    what error results on timeout?

25. **How do you know tests make no live calls?**
    All clients/fetchers are mocked/injected; one test asserts the client is
    never constructed in a dry run. *Inspect:* `tests/test_jailbreak_runner.py`.
    *Follow-up:* how would a stray real call show up?

26. **What is the difference between reported and calculated cost?**
    Reported comes from OpenRouter's usage; calculated is derived locally from
    token counts and live pricing, labelled an estimate. *Inspect:*
    `pricing_service.py`. *Follow-up:* what if pricing is missing?

27. **How is spreadsheet formula injection prevented?**
    Any cell starting with `= + - @` (or tab/CR) is prefixed with a quote so
    Excel/LibreOffice treat it as text. *Inspect:*
    `run_jailbreak_tests.py::sanitize_cell`. *Follow-up:* why does that preserve
    meaning?

28. **What exactly is in the jailbreak workbook?**
    A Summary sheet (totals, pass rate) and a Detailed sheet (29 cases, 11
    columns). Current: 29/29, 21 blocked, 1 warn, 7 allow, 21 prevented.
    *Inspect:* `evaluations/jailbreak_test_results.xlsx`. *Follow-up:* which
    category failed at Phase 10?

29. **How many prompt techniques, and are they really different?**
    Five, each with a distinct method block; a test asserts exactly five.
    *Inspect:* `src/prompts.py`, `tests/test_prompts.py`. *Follow-up:* which two
    are most similar and why?

30. **Do any prompts request hidden chain-of-thought?**
    No — the structured procedure asks for a visible method and only the final
    output; a test forbids reasoning-reveal phrases. *Inspect:*
    `tests/test_prompts.py`. *Follow-up:* why avoid hidden reasoning?

31. **How does the state machine stop skipping required data?**
    Each operation is legal only from specific states (e.g. a report needs
    `INTERVIEW_COMPLETE` with evidence). *Inspect:* `session_manager.py`,
    `report_service.py`. *Follow-up:* can you generate a report with no answers?

32. **What happens on an error mid-interview?**
    `enter_error` records a safe message and the state to return to;
    `recover_from_error` restores it — the session is not bricked. *Inspect:*
    `session_manager.py::TestErrorRecovery`. *Follow-up:* does a retry duplicate
    an answer?

33. **How is reset safe?**
    It rebuilds the session (clearing interview data) but keeps harmless
    developer preferences, behind a confirmation. *Inspect:*
    `session_manager.py::reset_interview`, `app.py::render_reset`. *Follow-up:*
    what survives a reset?

34. **Why Pydantic v2 `SecretStr` for the key?**
    It masks the value in reprs/logs so an accidental print cannot leak it.
    *Inspect:* `config.py`. *Follow-up:* what does `SecretStr` not protect
    against?

35. **What is the biggest residual risk?**
    Non-Base64 encoded injections and general model unpredictability; mitigated
    architecturally, not eliminated. *Inspect:* `docs/limitations.md`,
    `docs/security.md`. *Follow-up:* how would you measure the guard's real-world
    effectiveness?

36. **Why 450 tests — what do they actually cover?**
    Models, prompts, security, client, pricing, parser, services, session
    machine, UI smoke, generic professions and the experiments — all offline.
    *Inspect:* `tests/`. *Follow-up:* which area has the most edge cases?

37. **Could two users share state?**
    No — state is per Streamlit browser session in memory; there is no shared
    store or database. *Inspect:* `session_manager.py`. *Follow-up:* what would
    multi-user require?

---

## Part 2b — Interview Deep Dive (branching)

**Why did you implement branching?** Real interviews are not purely linear.
Strong interviewers probe an answer, challenge assumptions, request evidence or
explore consequences. Interview Deep Dive models that behaviour while keeping the
main interview sequence intact.

- **How does branching differ from a normal follow-up?** A follow-up is the
  single next main question; a Deep Dive is a *bounded side-thread* (up to two
  levels) anchored to a specific parent question and the candidate's actual
  answer, that returns to the main interview without advancing its progress.
- **How do you prevent infinite branching?** `MAX_BRANCH_DEPTH = 2`;
  `add_branch_question` refuses beyond the cap and the UI disables "Go deeper".
- **How is branch state represented?** Dedicated fields on `SessionData`
  (`branch_active`, `branch_questions`, …) and two sub-states
  (`BRANCH_AWAITING_ANSWER`, `BRANCH_EVALUATING`) in the same state machine.
- **Why don't branch questions increment interview progress?** The branch never
  touches `current_question_number` or the main lists, and the main progress
  operations are blocked while a branch is active — so "Question 2 of 6" stays
  correct after any number of deep dives.
- **How are branch costs tracked?** Each branch model call returns a
  `UsageRecord` recorded once (guarded by `begin_operation` against reruns), the
  same as the main flow.
- **How does security apply to a branch?** Branch answers are untrusted data
  (framed, never executed); context is injection-screened; output is inspected —
  identical to the main interview, so a branch cannot become a chatbot.
- **How would this evolve in a later agentic version?** Sprint 2 could let the
  model *decide* when and how to branch (dynamic depth, retrieval-augmented
  follow-ups), with guardrails and a budget — but Sprint 1 keeps it explicit,
  candidate-controlled and bounded.
- **What prevents arbitrary encoded content from being decoded?** *(Deep Dive
  reuses the same parser/guard as the rest of the app — see Part 2, Q8.)*

*Inspect:* `src/session_manager.py`, `src/interview_service.py`
(`generate_branch_question`), `src/models.py` (`BranchQuestion`), `app.py`,
`tests/test_branching.py`.

## Part 3 — Rehearsal checklist

- [ ] I can give the two-minute intro without notes.
- [ ] I can trace one full request end to end in the code.
- [ ] I can explain each of the five techniques and show the message split.
- [ ] I can explain temperature, max tokens and model choice.
- [ ] I can explain the security guard and honestly state its limits.
- [ ] I can explain cost precedence and why estimates are not bills.
- [ ] I can explain how reruns are prevented from duplicating calls/costs.
- [ ] I can state what Sprint 1 excludes and why.
