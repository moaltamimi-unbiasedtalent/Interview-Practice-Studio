# Final Local Source Report

Measured values only — every number is a real count from the loaded stores or the inventory. Regenerate with `python scripts/final_source_report.py`.

## Counts

| Metric | Value |
|---|---|
| Files discovered in data/raw | 198 |
| Files mapped to known sources | 198 |
| Unresolved files | 0 |
| Configured sources | 29 |
| Sources found locally | 22 |
| Sources normalised (records>0) | 19 |
| Sources indexed (vector chunks>0) | 11 |
| Sources retrieval-ready (total) | 26 |
| Sources production-ready (real data) | 11 |
| Real-data sources | 21 |
| Fixture-only sources | 5 |
| Structured occupation records | 8,035 |
| Task records | 22,339 |
| Skill relationships | 111,455 |
| Technology relationships | 11,572 |
| Knowledge records | 6,968 |
| Activity records | 20,141 |
| Occupation relationships | 12,016 |
| Competency records | 2,275 |
| Role-behaviour records | 5 |
| Qualification records | 3 |
| Compensation records | 1,920 |
| Labour-market records | 2,973 |
| Credential records | 5 |
| Vector documents (narrative files indexed) | 16 |
| Vector chunks | 3,528 |
| Manual acquisition still outstanding | 2 |
| Licence review still outstanding | 2 |
| Configured but not found locally | 2 |

## Configured but not found locally

- `ba_entgeltatlas` — Entgeltatlas (acquisition: manual)
- `berufenet` — BERUFENET occupation information (acquisition: manual)

## Data origin & production readiness (measured)

`retrieval-ready` = loaded locally; `production-ready` = real official data with a clear licence. Synthetic fixtures are never production-ready.

| Source | Origin | Fixture-only | Production-ready | Records |
|---|---|---|---|---|
| `ba_kompetenzkatalog` | synthetic_fixture | yes | no | 3 |
| `bls_oews` | official_local | no | yes | 1,393 |
| `bls_ooh` | official_local | no | yes | 343 |
| `bls_projections` | official_local | no | yes | 2,493 |
| `cedefop_clssi` | official_local | no | no | 1,178 |
| `cedefop_future_job_openings` | synthetic_fixture | yes | no | 2 |
| `cedefop_shortage_index` | synthetic_fixture | yes | no | 3 |
| `cedefop_skills_forecast` | authorised_manual | no | no | 2 |
| `digcomp` | mixed | no | no | 17 |
| `ecf` | synthetic_fixture | yes | no | 3 |
| `eqf` | authorised_manual | no | no | 0 |
| `esco` | official_local | no | no | 3,039 |
| `esco_handbook` | authorised_manual | no | no | 0 |
| `esco_matrix` | authorised_manual | no | no | 0 |
| `eurostat_earnings` | official_local | no | yes | 0 |
| `eurostat_occ_vacancy` | official_local | no | yes | 126 |
| `isco08` | official_local | no | no | 613 |
| `kldb` | official_local | no | no | 2,193 |
| `nice_framework` | official_local | no | yes | 2,252 |
| `onet` | official_local | no | yes | 1,016 |
| `ons_ashe` | official_local | no | yes | 527 |
| `opm_occupational_groups` | official_local | no | yes | 0 |
| `opm_qualification_standards` | synthetic_fixture | yes | no | 3 |
| `uk_civil_service_success_profiles` | authorised_manual | no | yes | 5 |
| `uk_hr_success_profiles` | authorised_manual | no | yes | 0 |
| `wef_future_of_jobs` | authorised_manual | no | no | 0 |

### Fixture-only sources (NOT production-ready)

- `ba_kompetenzkatalog` — served by a synthetic sample pending a real extract
- `cedefop_future_job_openings` — served by a synthetic sample pending a real extract
- `cedefop_shortage_index` — served by a synthetic sample pending a real extract
- `ecf` — served by a synthetic sample pending a real extract
- `opm_qualification_standards` — served by a synthetic sample pending a real extract

## Recommended sources still missing

- BERUFENET authorised export (German occupation detail beyond KldB)
- BA Entgeltatlas authorised export (German compensation)
- Real extracts to replace fixture-only competency/labour samples (e-CF, BA Kompetenzkatalog, OPM qualification standards, Cedefop openings/shortage)
