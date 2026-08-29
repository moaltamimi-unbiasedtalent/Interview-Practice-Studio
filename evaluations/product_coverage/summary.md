# Product Coverage Benchmark

**412 labelled candidate questions** over the production-ready real career-knowledge sources. Deterministic run.
Embedding mode: **lexical/offline (local hash embedder)**.

Does not modify the 11R / 11R-A / KB-2 architecture benchmarks.

## Metrics vs product gates

| Metric | Score | n | Gate | Pass |
|---|---|---|---|---|
| routing | 100% | 412 | 95% | ✅ |
| occupation_resolution | 94% | 310 | — | — |
| geo_source | 95% | 192 | 95% | ✅ |
| evidence_hit@5 | 94% | 412 | 90% | ✅ |
| citation_validity | 100% | 88 | 100% | ✅ |
| provenance_completeness | 100% | 201 | — | — |
| salary_context | 100% | 14 | 100% | ✅ |
| year_correctness | 100% | 35 | — | — |
| tool_selection | 100% | 24 | 95% | ✅ |
| insufficient_evidence | 97% | 412 | 95% | ✅ |
| unsupported_claim | 100% | 8 | — | — |

Latency (structured retrieval): p50 28.92 ms · p95 52.4 ms.

## Coverage by question family

| Question family | Cases | Routing | Covered (Hit@5 / gap-ok) |
|---|---|---|---|
| annual_openings | 32 | 100% | 91% |
| candidate_gap | 8 | 100% | 100% |
| career_transition | 6 | 100% | 100% |
| certifications | 12 | 100% | 100% |
| compensation | 32 | 100% | 75% |
| current_demand | 32 | 100% | 100% |
| cybersecurity | 2 | 50% | 50% |
| digital_competency | 12 | 100% | 100% |
| education | 12 | 100% | 67% |
| experience | 12 | 100% | 100% |
| future_growth | 32 | 100% | 91% |
| industry_context | 12 | 100% | 100% |
| interview_themes | 8 | 100% | 100% |
| knowledge | 12 | 100% | 100% |
| leadership | 12 | 100% | 100% |
| licences | 12 | 100% | 100% |
| preparation_plan | 8 | 100% | 100% |
| responsibilities | 12 | 100% | 100% |
| role_definition | 12 | 100% | 100% |
| seniority | 12 | 100% | 100% |
| short_term_outlook | 32 | 100% | 91% |
| shortages | 32 | 100% | 97% |
| skills | 12 | 100% | 100% |
| tasks | 12 | 100% | 100% |
| technology | 12 | 100% | 100% |
| training | 12 | 100% | 100% |
| unsupported | 8 | 88% | 100% |

## Coverage by geography

| Geography | Cases | Geo-source correct | Covered |
|---|---|---|---|
| DE | 48 | 98% | 98% |
| EU | 48 | 100% | 100% |
| UK | 48 | 90% | 88% |
| US | 48 | 94% | 77% |

## Source routing (evidence provenance)

- `esco` — 54 cases
- `bls_projections` — 39 cases
- `eurostat_occ_vacancy` — 32 cases
- `isco08` — 25 cases
- `bls_oews` — 23 cases
- `onet` — 19 cases
- `bls_ooh` — 17 cases
- `uk_civil_service_success_profiles` — 12 cases
- `digcomp` — 12 cases
- `ons_ashe` — 7 cases
- `cedefop_future_job_openings` — 4 cases
- `careeronestop` — 3 cases
- `cedefop_skills_forecast` — 2 cases
- `cedefop_shortage_index` — 2 cases
- `nice_framework` — 1 cases
