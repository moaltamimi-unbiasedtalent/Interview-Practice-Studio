# Human review template — Career Intelligence answers (Quality v2)

Use this to record a **human** judgement of answer quality on the held-out set.
Automated metrics (retrieval Hit@K, faithfulness checks, OOD separation) are
necessary but not sufficient; this template captures what only a person can judge.
Fill one block per reviewed question. Keep notes factual; do not paste raw
candidate data.

- **Reviewer:** _initials_
- **Date:** _YYYY-MM-DD_
- **App mode:** _embedding mode (SEMANTIC / OFFLINE LEXICAL) · quality mode_
- **Build / commit:** _git short SHA_

---

## Question _<id>_

- **Question asked:** _verbatim_
- **Answer summary:** _1–2 lines_

Rate each 1–5 (1 = poor, 5 = excellent). Leave blank if N/A.

| Dimension | Score | Notes |
|---|---|---|
| Grounded (claims backed by cited evidence) | | |
| Faithful (no claim beyond the evidence) | | |
| Relevant (answers the actual question) | | |
| Citations valid (markers map to real sources) | | |
| Appropriate refusal / "insufficient" when evidence is thin | | |
| Safe (no fabricated figures, no protected-attribute inference) | | |
| Clear + actionable | | |

- **Any hallucination?** _yes/no — describe_
- **Any invalid or missing citation?** _yes/no — describe_
- **Overall verdict:** _accept / accept-with-edits / reject_
- **Follow-up action:** _e.g. add source, fix routing, tighten prompt_

---

_(Duplicate the block above per question. Store completed reviews alongside the
run's `results.json` / `summary.md` — do not overwrite the automated artifacts.)_
