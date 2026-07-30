# Quality report — Interview Practice Studio (Phase 11)

## 1. Executive quality status

**PASS WITH DOCUMENTED LIMITATIONS.** All mandatory functionality is intact and
covered by automated tests; the full suite passes with no live network calls
and no real credentials. One defect was found and fixed (the Phase-10 Base64
injection gap, JB-22), narrowed with a bounded, tested improvement. Remaining
items are honestly documented residual risks (non-Base64 encodings) and manual
UX checks, not unresolved defects.

## 2. Baseline commit

`6be8f178e8d2c987485a70fcc055ce675b1d8c23` — *test: add jailbreak and input
security evaluation* (414 tests passing, working tree clean, HEAD == origin).

## 3. Audit scope

Areas A–O: functional correctness, generic-profession support, Streamlit
behaviour, state-machine correctness, OpenRouter request construction,
structured-output handling, security & privacy (incl. the Base64 residual
risk), pricing & usage, prompt-engineering, accessibility, code quality,
dependency & configuration health, generated evaluation artefacts, automated
tests, and documentation accuracy.

## 4. Commands run

- `git rev-parse` / `git status` / `git fetch` (pre-flight; clean, in sync).
- `python -m pytest` (baseline 414 → final 450); focused runs per change.
- `python -m pip check` (no broken requirements).
- `python -m py_compile` over `src/`, `app.py`, `scripts/`, `tests/`.
- Import checks for every module.
- Manual AST scan for unused imports; grep scans for TODO/FIXME/print/eval/
  exec/bare-except/keys/paths/globals/mutable-defaults/streamlit-in-services.
- Streamlit headless smoke: `streamlit run app.py --server.headless true`
  (HTTP 200, 0 OpenRouter requests, 0 tracebacks, stopped cleanly).
- Workbook validation (`openpyxl`), CSV read, secret-pattern scan of generated
  files.

## 5. Defects found

| ID | Severity | Area | Description |
|----|----------|------|-------------|
| D-1 | Medium | Security (G) | Phase-10 JB-22: a high-confidence Base64-wrapped injection was not detected by the deterministic guard (documented residual risk). |

No Critical or High defects were found. No other Medium/Low defects were found;
static scans, dependency checks and the existing test coverage were clean.

## 6. Fixes implemented

- **D-1 (root cause):** `detect_injection` scored only the surface text; an
  attacker could Base64-encode an instruction so no plaintext indicator matched.
  **Fix (smallest correct):** decode **only** high-confidence, standalone Base64
  segments (length 20–256, valid padding, decodes to ≥90%-printable UTF-8;
  capped at 5 segments / 1000 chars) and re-scan the decoded text with the
  *same* injection scanner. Decoded bytes are only treated as text — never
  executed. Non-Base64 tokens, hashes, binary blobs and benign Base64 are
  unaffected.

## 7. Regression tests added

- `tests/test_security.py::TestBase64Injection` (6 cases): Base64-wrapped
  injection blocks; benign Base64 sentence / identifier / hex-hash / binary
  blob stay `allow`; a Base64 "Python-like" payload is not executed (allowed,
  not run).
- `tests/test_generic_professions.py` (30 cases): configuration, neutral-system
  prompt construction, and mocked evaluation across ten professions.

## 8. Functional verification

Covered by existing + new tests (no live calls): interview setup and
job-description context (`test_app_smoke`, `test_interview_service`); strategy,
multi-turn questions, evaluation, follow-ups, final report
(`test_interview_service`, `test_evaluation_service`, `test_report_service`);
JSON & Markdown download and reset (`test_app_smoke`, `test_ui_helpers`);
usage/cost display (`test_pricing_service`); Prompt Lab and five techniques
(`test_prompt_comparison`, `test_prompts`); three approved models
(`test_config`, `test_models`).

## 9. Security verification

Input normalisation/length, direct & indirect injection, scope enforcement,
untrusted-content wrapping, output-leakage and secret-like output detection,
spreadsheet formula-injection protection, and privacy notices are covered by
`test_security.py` and `test_jailbreak_runner.py`. The jailbreak battery is
**29 cases / 16 categories**, now **29/29** after the Base64 fix (21 blocked,
1 warn, 7 allow, 21 model calls prevented). No persistent interview storage; no
real secrets in source, tests, docs, evaluation output, or the generated
workbook/CSV (secret-pattern scan clean; only dummy `TEST_API_KEY`).

## 10. Streamlit verification

Headless start confirmed (HTTP 200 on `/_stcore/health`), no OpenRouter request
made, process stopped cleanly. `AppTest` covers startup and the strategy,
report, error and Prompt Lab states offline; Prompt-Lab run buttons stay
disabled until confirmed.

## 11. Generic-profession verification

`tests/test_generic_professions.py` drives ten professions (Junior Software
Developer, Senior Accountant, Registered Nurse, Electrician, Operations
Manager, Marketing Director, Teacher, Compliance Manager, Sales Manager, CEO)
and asserts the system prompt stays neutral ("every profession") while the role
appears only in the user message — no HR/software/other-discipline assumption.

## 12. Evaluation-artefact verification

`evaluations/prompt_comparison.{md,json}` and
`evaluations/model_settings_comparison.{md,json}` are present and readable
(status `completed` — real runs, distinguishable from placeholders by the
`status` field). `jailbreak_test_results.csv` is valid (29 rows, 11 columns);
`jailbreak_test_results.xlsx` opens programmatically with `Summary` and
`Detailed results` sheets. No cell begins with a formula character; no
secret-like real values present; no fabricated live-model results.

## 13. Test totals

Baseline **414** → final **450** passing (+36: 6 Base64 regression, 30
generic-profession). `python -m pip check`: no broken requirements.

## 14. Known limitations

- The deterministic guard is best-effort pattern matching; it does not stop
  every jailbreak.
- Base64 decoding is intentionally narrow (high-confidence, standalone, bounded)
  and does not cover other encodings or nested/split Base64.
- Live model behaviour behind the guard is not automatically tested (requires
  the gated `--run-live --confirm` path).

## 15. Residual risks

- Encoded injections other than high-confidence Base64 (URL/hex/ROT13, nested,
  whitespace-split) rely on the architectural data-framing defence.
- False positives are possible in principle for pattern-based detection
  (mitigated by benign/technical test cases).
- Model responses are semi-trusted; `inspect_output` scans for leakage and
  secret-like output but cannot guarantee model behaviour.

## 16. Manual checks still required

- Visual/UX review in a browser (heading hierarchy, colour-independent cues,
  keyboard navigation) beyond automated structure checks.
- Screen-reader spot check of labels and help text.
- A real, confirmed live run of Prompt Lab / jailbreak live-assist to record
  qualitative model behaviour (optional, chargeable).

## 17. Phase 12 readiness

Ready. Functionality intact, suite green, no live calls, no real credentials,
no unresolved Critical/High/Medium defects (D-1 fixed), Streamlit starts
cleanly, and the working tree contains only intended Phase 11 changes.

## 18. Status

**PASS WITH DOCUMENTED LIMITATIONS.**
