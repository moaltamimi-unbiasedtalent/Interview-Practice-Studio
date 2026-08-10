# Screenshots checklist

Capture these eight screenshots from a real local run and save them here with
the exact filenames below. **Do not fabricate screenshots** — only add a file
once you have genuinely captured it. Exclude any real API key, secret, or
confidential content from every image (the app never displays the key, but
double-check the sidebar and browser address bar).

macOS capture: `Shift-Cmd-4` (drag a region) or `Shift-Cmd-4` then `Space`
(a single window). Files save to the Desktop by default; move/rename them here.

| # | Filename | App state to capture | Exclude | What it proves | Recommended crop | Manual test IDs |
|---|---|---|---|---|---|---|
| 1 | `01_setup_form.png` | Setup form filled in (role + job description + a few options) | Real employer names if sensitive | Interview setup and job-description context work | Main setup panel | 16, 17, 88, 91, 98 |
| 2 | `02_interview_strategy.png` | Role-analysis / strategy view after "Generate strategy" | — | Strategy generation and structured display | Strategy panel (both columns) | 42, 90 |
| 3 | `03_mock_interview.png` | Chat interview showing one question and a submitted answer | — | Multi-turn chat + progress indicator | Chat area + progress bar | 43, 44, 49, 50 |
| 4 | `04_answer_feedback.png` | Structured feedback: overall + seven scores, lists, improved example | — | Rubric feedback, labelled example, follow-up | Feedback block incl. score row | 45, 46, 47, 48 |
| 5 | `05_final_report.png` | Final report with JSON + Markdown download buttons visible | — | Report grounded in evidence + downloads | Report panel + download buttons | 54, 55, 56, 57 |
| 6 | `06_prompt_lab.png` | Prompt Lab view with the charge warning + confirmation checkbox (Run disabled) | — | Prompt Lab is separated and gated | Prompt Lab panel incl. warning | 99, 100, 101 |
| 7 | `07_usage_cost.png` | Sidebar usage panel: model, tokens, current + cumulative cost, reported/estimated | Real key (never shown) | Usage & cost reporting incl. reported-vs-estimated | Sidebar usage section | 61, 62, 63, 64, 65, 66, 67 |
| 8 | `08_jailbreak_workbook.png` | `evaluations/jailbreak_test_results.xlsx` open on the Summary sheet | — | Reproducible security evidence (29/29) | Summary sheet metrics | 104, 105, 106 |

After adding the files, update the README `Screenshots` section to reference
them, and mark the related manual test rows with the screenshot as evidence.
