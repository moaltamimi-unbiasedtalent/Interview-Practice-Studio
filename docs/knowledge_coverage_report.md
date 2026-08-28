# Knowledge Coverage Report

Measured from the loaded structured stores — every number is a real row count, never an estimate. Only sources with data actually loaded are listed as active coverage.

## Headline counts

- Retrieval-ready total: **26** (anything loaded locally, real or fixture)
- Production-ready real-data total: **11** (real official data with a clear licence)
- Real-data sources: **21** · Fixture-only: **5**

## Coverage by area (measured)

### Occupations
- ESCO — Occupations & Skills (`esco`) — 3,039 records
- Klassifikation der Berufe (KldB) (`kldb`) — 2,193 records
- O*NET Database (`onet`) — 1,016 records
- BLS Employment Projections (`bls_projections`) — 831 records
- ISCO-08 Classification of Occupations (`isco08`) — 613 records
- Occupational Outlook Handbook (OOH) (`bls_ooh`) — 343 records

### Responsibilities / tasks
- O*NET Database (`onet`) — 17,939 records
- ISCO-08 Classification of Occupations (`isco08`) — 4,400 records

### Skills
- ESCO — Occupations & Skills (`esco`) — 93,974 records
- O*NET Database (`onet`) — 17,481 records

### Knowledge
- O*NET Database (`onet`) — 6,968 records

### Work activities / context
- O*NET Database (`onet`) — 20,141 records

### Technologies
- O*NET Database (`onet`) — 11,572 records

### Career transitions (relationships)
- O*NET Database (`onet`) — 9,230 records
- Klassifikation der Berufe (KldB) (`kldb`) — 2,183 records
- ISCO-08 Classification of Occupations (`isco08`) — 603 records

### Competencies
- NICE Workforce Framework for Cybersecurity (`nice_framework`) — 2,252 records
- DigComp — European Digital Competence Framework (`digcomp`) — 17 records
- BA Kompetenzkatalog (`ba_kompetenzkatalog`) — 3 records — 🧪 FIXTURE
- European e-Competence Framework (e-CF) (`ecf`) — 3 records — 🧪 FIXTURE

### Seniority / interview behaviours
- UK Civil Service Success Profiles (`uk_civil_service_success_profiles`) — 5 records

### Qualification requirements
- OPM General Schedule Qualification Standards (`opm_qualification_standards`) — 3 records — 🧪 FIXTURE

### Compensation
- Occupational Employment and Wage Statistics (OEWS) (`bls_oews`) — 1,393 records
- Annual Survey of Hours and Earnings (ASHE) (`ons_ashe`) — 527 records

### Future demand (forecast)
- BLS Employment Projections (`bls_projections`) — 831 records
- Cedefop Skills Forecast (`cedefop_skills_forecast`) — 2 records

### Future job openings
- BLS Employment Projections (`bls_projections`) — 831 records
- Cedefop Future Job Openings (`cedefop_future_job_openings`) — 2 records — 🧪 FIXTURE

### Shortages
- Cedefop Labour & Skills Shortage Index (CLSSI) (`cedefop_clssi`) — 1,178 records
- Cedefop Labour & Skills Shortage Index (`cedefop_shortage_index`) — 3 records — 🧪 FIXTURE

## Acquisition lists

### 1. Available locally and current
- `ba_kompetenzkatalog` — lifecycle AVAILABLE, 3 records, version — (VERSION_UNKNOWN)
- `bls_oews` — lifecycle AVAILABLE, 1,393 records, version M2025 (VERSION_UNKNOWN)
- `bls_ooh` — lifecycle AVAILABLE, 343 records, version 2025 (VERSION_UNKNOWN)
- `bls_projections` — lifecycle AVAILABLE, 2,493 records, version 2025-2035 (VERSION_UNKNOWN)
- `cedefop_clssi` — lifecycle AVAILABLE, 1,178 records, version 2026 (VERSION_UNKNOWN)
- `cedefop_future_job_openings` — lifecycle AVAILABLE, 2 records, version — (VERSION_UNKNOWN)
- `cedefop_shortage_index` — lifecycle AVAILABLE, 3 records, version — (VERSION_UNKNOWN)
- `cedefop_skills_forecast` — lifecycle AVAILABLE, 2 records, version 2026 (VERSION_UNKNOWN)
- `cedefop_stas` — lifecycle LOCAL FILE FOUND, 0 records, version Jan 2026 (VERSION_UNKNOWN)
- `digcomp` — lifecycle AVAILABLE, 17 records, version 2.2 (VERSION_UNKNOWN)
- `ecf` — lifecycle AVAILABLE, 3 records, version — (VERSION_UNKNOWN)
- `eqf` — lifecycle AVAILABLE, 0 records, version brochure (VERSION_UNKNOWN)
- `esco` — lifecycle AVAILABLE, 3,039 records, version v1.2.1 (CURRENT)
- `esco_handbook` — lifecycle AVAILABLE, 0 records, version Sept 2017 (VERSION_UNKNOWN)
- `esco_matrix` — lifecycle AVAILABLE, 0 records, version v1.2.1 (CURRENT)
- `eurostat_earnings` — lifecycle AVAILABLE, 0 records, version SES 2022 (VERSION_UNKNOWN)
- `eurostat_occ_vacancy` — lifecycle AVAILABLE, 126 records, version jvs_a_isco3_r1 (VERSION_UNKNOWN)
- `isco08` — lifecycle AVAILABLE, 613 records, version ISCO-08 (CURRENT)
- `kldb` — lifecycle AVAILABLE, 2,193 records, version 2010 (Fassung 2020) (VERSION_UNKNOWN)
- `nice_framework` — lifecycle AVAILABLE, 2,252 records, version v2.2.0 (VERSION_UNKNOWN)
- `onet` — lifecycle AVAILABLE, 1,016 records, version 31.0 (CURRENT)
- `ons_ashe` — lifecycle AVAILABLE, 527 records, version 2025 provisional (VERSION_UNKNOWN)
- `opm_occupational_groups` — lifecycle AVAILABLE, 0 records, version TS-107 1991 (VERSION_UNKNOWN)
- `opm_qualification_standards` — lifecycle AVAILABLE, 3 records, version — (VERSION_UNKNOWN)
- `uk_civil_service_success_profiles` — lifecycle AVAILABLE, 5 records, version v0f (VERSION_UNKNOWN)
- `uk_hr_success_profiles` — lifecycle AVAILABLE, 0 records, version v0e (VERSION_UNKNOWN)
- `wef_future_of_jobs` — lifecycle AVAILABLE, 0 records, version 2025 (VERSION_UNKNOWN)

### 2. Available locally but outdated
- _none detected_

### 3. Configured but NOT found locally
- `ba_entgeltatlas` — Entgeltatlas (acquisition: manual)
- `berufenet` — BERUFENET occupation information (acquisition: manual)

### 4. Recommended sources not yet available
- BLS Occupational Outlook Handbook structured export (adds US outlook narrative + entry education)
- BERUFENET authorised export (adds German occupation detail beyond KldB)
- BA Entgeltatlas authorised export (adds German compensation, currently sample-only)

## Version notes (offline)

Local versions are reported as detected; latest official versions were **not fetched live** (local-first, no network). Nothing is auto-updated.

| Source | Local version | Known latest | Class |
|---|---|---|---|
| `ba_kompetenzkatalog` | — | — | VERSION_UNKNOWN |
| `bls_oews` | M2025 | — | VERSION_UNKNOWN |
| `bls_ooh` | 2025 | — | VERSION_UNKNOWN |
| `bls_projections` | 2025-2035 | — | VERSION_UNKNOWN |
| `cedefop_clssi` | 2026 | — | VERSION_UNKNOWN |
| `cedefop_future_job_openings` | — | — | VERSION_UNKNOWN |
| `cedefop_shortage_index` | — | — | VERSION_UNKNOWN |
| `cedefop_skills_forecast` | 2026 | — | VERSION_UNKNOWN |
| `cedefop_stas` | Jan 2026 | — | VERSION_UNKNOWN |
| `digcomp` | 2.2 | — | VERSION_UNKNOWN |
| `ecf` | — | — | VERSION_UNKNOWN |
| `eqf` | brochure | — | VERSION_UNKNOWN |
| `esco` | v1.2.1 | v1.2.1 | CURRENT |
| `esco_handbook` | Sept 2017 | — | VERSION_UNKNOWN |
| `esco_matrix` | v1.2.1 | v1.2.1 | CURRENT |
| `eurostat_earnings` | SES 2022 | — | VERSION_UNKNOWN |
| `eurostat_occ_vacancy` | jvs_a_isco3_r1 | — | VERSION_UNKNOWN |
| `isco08` | ISCO-08 | ISCO-08 | CURRENT |
| `kldb` | 2010 (Fassung 2020) | — | VERSION_UNKNOWN |
| `nice_framework` | v2.2.0 | — | VERSION_UNKNOWN |
| `onet` | 31.0 | 31.0 | CURRENT |
| `ons_ashe` | 2025 provisional | — | VERSION_UNKNOWN |
| `opm_occupational_groups` | TS-107 1991 | — | VERSION_UNKNOWN |
| `opm_qualification_standards` | — | — | VERSION_UNKNOWN |
| `uk_civil_service_success_profiles` | v0f | — | VERSION_UNKNOWN |
| `uk_hr_success_profiles` | v0e | — | VERSION_UNKNOWN |
| `wef_future_of_jobs` | 2025 | — | VERSION_UNKNOWN |
