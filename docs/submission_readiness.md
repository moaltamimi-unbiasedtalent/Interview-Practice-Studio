# Interview OS Coach — Submission Readiness

Final pre-submission audit (Phase 14R). Evidence-based; verdict at the end.

> **Current numbers are generated, not hand-maintained.** Test counts, source
> counts and coverage figures throughout this document reflect the phase they were
> written in. For the **current measured state** see
> [metrics_snapshot.md](metrics_snapshot.md) (regenerate with
> `python scripts/gen_metrics.py`) and the overall verdict in
> [career_intelligence_production_readiness.md](career_intelligence_production_readiness.md).
> Historical 11R / 11R-A / KB-2 figures below are kept as-is on purpose.

## Current sprint scope

The **Building Applications with AI** sprint deliverable is the **Career
Intelligence** module (LangChain + advanced RAG + embeddings + vector/hybrid +
query translation + structured retrieval + tool calling + domain security, in
Streamlit over OpenRouter). **Interview Practice** pre-existed and is not part of
the sprint; it provides the real-world use case the sprint work plugs into.

## Core requirements

| Requirement | Status |
| --- | --- |
| **RAG — domain knowledge base** | PASS |
| **RAG — embeddings** | PASS |
| **RAG — chunking** | PASS |
| **RAG — vector similarity search** | PASS |
| **RAG — query translation** | PASS |
| **RAG — structured retrieval** | PASS |
| **Tool Calling — ≥3 tools** | PASS (4 tools) |
| **Tool Calling — domain relevance** | PASS |
| **Tool Calling — tool execution** | PASS |
| **Tool Calling — tool visibility** | PASS |
| **Domain — focused domain** | PASS |
| **Domain — relevant data** | PASS |
| **Domain — domain prompts** | PASS |
| **Domain — domain security** | PASS |
| **Technical — LangChain** | PASS |
| **Technical — OpenRouter** | PASS |
| **Technical — error handling** | PASS |
| **Technical — validation** | PASS |
| **UI — Streamlit** | PASS |
| **UI — sources** | PASS |
| **UI — context** | PASS |
| **UI — tool results** | PASS |
| **UI — progress states** | PASS |

No core requirement is PARTIAL or FAIL.

## Optional requirements (working evidence required)

| Optional task | Tier | Status | Evidence |
| --- | --- | --- | --- |
| Prompt-injection protection | medium | PASS | `src/copilot/security/*`; 30-case eval (100% detect, 0 FP); `test_copilot_security.py` |
| Token/cost tracking | medium | PASS | Career `UsageLedger` (tokens by op; cost honestly "unavailable"), Interview `PricingService` (reported→calculated→none); `test_core.py`, `test_career_history.py` |
| Conversation history/export | medium | PASS | history + JSON/CSV + combined export; `test_career_history.py` |
| Hybrid search | hard | PASS | vector + BM25 + RRF; `test_copilot_hybrid.py` |
| RAG evaluation | hard | PASS | 11R + 11R-A; `test_rag_eval.py`, `test_expanded_eval.py`, `evaluations/*` |

3 medium + 2 hard optional tasks complete (exceeds minimums).

## Knowledge architecture

| Component | Status | Note |
| --- | --- | --- |
| Structured Role DB | PASS | SQLite; ESCO/O*NET/ISCO/KldB normalisers; runnable from samples |
| Vector Knowledge | PASS | Chroma + in-memory fallback |
| Compensation DB | PASS | SQLite; context-preserving (currency/period/statistic/geo/year) |
| Retrieval router | PASS | deterministic lanes + LLM fallback; lane shown in RAG Inspector |
| Provenance | PASS | one model; authority levels; completeness 1.0 on samples |
| Source manifest | PASS | 11 sources; licence + acquisition flags; no guessed terms |

Source usability: auto-downloadable sources (O*NET, OEWS, ASHE, Eurostat) fetch
via `scripts/download_sources.py`; the rest are flagged
`manual_acquisition_required`. Committed synthetic samples let the whole pipeline
run without downloads.

## Test evidence

- **Python:** 963 passed, 1 skipped, 0 failed.
- **Frontend (vitest):** 10 passed (2 files).
- **Compile:** OK. **Imports:** OK. **Streamlit smoke:** 6/6 routes boot.
- **Secret scan (working tree):** clean.

## Baseline RAG evaluation (11R)

33 cases, top_k=5, committed synthetic corpus, local embedder:

| mode | Hit@5 | MRR | Recall@5 |
| --- | --- | --- | --- |
| vector | 0.97 | 0.842 | 0.955 |
| keyword | 0.97 | 0.904 | 0.97 |
| hybrid | 0.939 | 0.871 | 0.924 |

Tool selection 1.0; citation validity 1.0. Honest finding: on this corpus with a
lexical embedder, **keyword edges out hybrid** — reported, not rewritten.

## Expanded architecture evaluation (11R-A)

- Routing accuracy **1.0** (per-lane: structured_role, compensation, forecast,
  vector, mixed).
- Structured-role retrieval: hit **1.0**, provenance **1.0**.
- Compensation: accuracy **1.0** (country+year+currency+statistic+source),
  provenance **1.0**; wrong geography/year scored incorrect.
- Baseline comparison: core vector/keyword/hybrid **Δ = 0** — the expansion adds
  lanes/coverage, it does not change narrative retrieval. No improvement claimed
  where the numbers do not show one. 11R artifacts preserved in
  `evaluations/baseline/`.

## Security

- No real API keys, Google credential JSON, real `.env` or real `secrets.toml`
  committed (only `.streamlit/secrets.toml.example`). The two `sk-or-…` strings
  in git history are **dummy test fixtures** (`tests/test_security.py`,
  `tests/test_copilot_security.py`), not real secrets — no real secret in history.
- Logging redacts candidate/JD/chunk/transcript/content; output guard redacts
  secret-like strings. No raw audio is persisted (Record is transient). No system-
  prompt leakage (output guard + tests). No cross-module trust escalation:
  injected JD/candidate/chunks stay untrusted data; PreparationContext is plain
  data (verified in `test_os_e2e.py`).
- Repo hygiene: a stray committed virtualenv was untracked in 12R.

## Source / licence status

Every source in `data/source_manifest.json` carries source, publisher,
version/year, storage target, provenance and a licence note. Unconfirmed licences
are flagged `licence_review_required` and treated as non-redistributable; no
datasets are committed. See `docs/source_licensing.md`.

## Known limitations

- Committed corpus/samples are synthetic, so absolute eval numbers are
  illustrative; real datasets require manual acquisition + licence confirmation.
- Offline/local embedder is lexical; semantic vector quality needs an OpenAI key.
- Deterministic injection defence is best-effort, not a guarantee.
- Structured lanes (role/competency/compensation/labour-market) now participate
  in the production chat answer via the StructuredRetrievalCoordinator, merged with
  vector RAG and cited; occupation resolution + geographic source precedence apply.
- Live LLM/Speech/Gemini paths need credentials and are not exercised in CI.

## Manual checks remaining

From `docs/manual_acceptance_test.md` (80 checks: ~72 PASS, 0 FAIL, remaining NOT
TESTED). Outstanding items all require live credentials or a full manual session:

- Grounded chat answer with a real model (live).
- Interview strategy / dynamic questions / Deep Dive with a live model.
- Record mode with Google Speech; Live mode with Gemini (fallbacks verified).
- Full accessibility audit (desktop + 900px already verified).

## Final verdict

**READY WITH MINOR MANUAL CHECKS**

Rationale: all core requirements PASS; 3 medium + 2 hard optional tasks PASS with
evidence; full automated suite green (963 + 10 frontend); no real secrets;
sources/licences documented; evaluation reported honestly. The only outstanding
items are live-provider manual checks that need credentials — their graceful
fallbacks are already verified.

## KB-2 addendum — authoritative knowledge expansion

After the audit above, the knowledge foundation was expanded (KB-2):

- **25 authoritative sources** across five stores (role, competency, compensation,
  labour-market, vector), each data type in the right store; full list in
  `docs/knowledge_source_catalogue.md`.
- **Measured source lifecycle** (`data/source_status.json`, regenerated by
  `python scripts/source_status.py`) — a manifest source is never implied loaded;
  16/25 read AVAILABLE from the committed offline samples, the rest honestly
  MANUAL ACQUISITION / LICENCE REVIEW.
- **New router lanes** (competency, cybersecurity, shortage, openings, transition,
  seniority) and **geographic source precedence**; existing lanes unchanged.
- **New evaluation** `evaluations/knowledge_expansion/` (routing 1.0, geographic
  precedence 1.0, coverage 16/25) — the 11R / 11R-A / baseline artifacts are
  preserved untouched.
- **Automated suite** now **1003 passed + 1 skipped** (Python) and **10** frontend;
  licence audit refreshed; no datasets or secrets committed.

Verdict is unchanged: **READY WITH MINOR MANUAL CHECKS** — the expansion adds
breadth, provenance and honest lifecycle reporting without destabilising Interview
Practice or the preserved evaluation baseline.
