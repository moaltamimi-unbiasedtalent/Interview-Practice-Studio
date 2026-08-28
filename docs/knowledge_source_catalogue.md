# Knowledge Source Catalogue

Authoritative sources for Career Intelligence, grouped by data type.
**Lifecycle and data origin are measured** (`data/source_status.json`).
Two counts matter: *retrieval-ready* (loaded locally, real or fixture) and
*production-ready* (real official data with a clear licence). Synthetic test
fixtures are never production-ready. Raw datasets are not committed.

## Summary

- Configured sources: **27**
- Retrieval-ready (total): **24**
- Production-ready (real data): **10**
- Real-data sources: **19** · Fixture-only: **5**
- Structured records: **13,899** · Vector chunks: **3,528**

Authority level is retrieval metadata (1 official · 2 public framework · 3 industry), **not** a truth score.

## Occupations & Role Data

| Source | Region | Auth | Version | Origin | Prod-ready | Lifecycle | Records | Chunks |
|---|---|---|---|---|---|---|---|---|
| O*NET Database | US | 1 | 31.0 | official_local | ✅ yes | AVAILABLE | 1,016 | 0 |
| ESCO — Occupations & Skills | EU | 1 | v1.2.1 | official_local | no | AVAILABLE | 3,039 | 0 |
| ISCO-08 Classification of Occupations | global | 1 | ISCO-08 | official_local | no | AVAILABLE | 613 | 0 |
| Klassifikation der Berufe (KldB) | DE | 1 | 2010 (Fassung 2020) | official_local | no | AVAILABLE | 2,193 | 0 |
| BERUFENET occupation information | DE | 1 | current release | — | no | MANUAL ACQUISITION | 0 | 0 |
| Occupational Outlook Handbook (OOH) | US | 1 | 2025 | official_local | ✅ yes | AVAILABLE | 343 | 0 |

## Skills & Competencies

| Source | Region | Auth | Version | Origin | Prod-ready | Lifecycle | Records | Chunks |
|---|---|---|---|---|---|---|---|---|
| ESCO Skills–Occupations Matrix | EU | 1 | v1.2.1 | authorised_manual | no | AVAILABLE | 0 | 33 |
| DigComp — European Digital Competence Framework | EU | 2 | 3.0 | authorised_manual | no | AVAILABLE | 9 | 462 |
| BA Kompetenzkatalog | DE | 1 | current release | synthetic_fixture | 🧪 fixture | AVAILABLE | 3 | 0 |
| European e-Competence Framework (e-CF) | EU | 2 | current release | synthetic_fixture | 🧪 fixture | AVAILABLE | 3 | 0 |

## Seniority & Job Architecture

| Source | Region | Auth | Version | Origin | Prod-ready | Lifecycle | Records | Chunks |
|---|---|---|---|---|---|---|---|---|
| European Qualifications Framework (EQF) | EU | 2 | brochure | authorised_manual | no | AVAILABLE | 0 | 78 |
| OPM Handbook of Occupational Groups and Families | US | 1 | TS-107 1991 | official_local | ✅ yes | AVAILABLE | 0 | 1,233 |
| OPM General Schedule Qualification Standards | US | 1 | current release | synthetic_fixture | 🧪 fixture | AVAILABLE | 3 | 0 |
| UK Civil Service Success Profiles | UK | 2 | v0f | authorised_manual | ✅ yes | AVAILABLE | 5 | 39 |

## Compensation

| Source | Region | Auth | Version | Origin | Prod-ready | Lifecycle | Records | Chunks |
|---|---|---|---|---|---|---|---|---|
| Occupational Employment and Wage Statistics (OEWS) | US | 1 | M2025 | official_local | ✅ yes | AVAILABLE | 1,393 | 0 |
| Annual Survey of Hours and Earnings (ASHE) | UK | 1 | 2025 provisional | official_local | ✅ yes | AVAILABLE | 527 | 0 |
| Eurostat Earnings (Structure of Earnings Survey) | EU | 1 | SES 2022 | official_local | ✅ yes | AVAILABLE | 0 | 85 |
| Entgeltatlas | DE | 1 | current release | — | no | MANUAL ACQUISITION | 0 | 0 |

## Labour Market & Forecasts

| Source | Region | Auth | Version | Origin | Prod-ready | Lifecycle | Records | Chunks |
|---|---|---|---|---|---|---|---|---|
| Cedefop Skills Forecast | EU | 1 | 2026 | authorised_manual | no | AVAILABLE | 2 | 71 |
| Cedefop Future Job Openings | EU | 1 | current release | synthetic_fixture | 🧪 fixture | AVAILABLE | 2 | 0 |
| Cedefop Labour & Skills Shortage Index | EU | 1 | current release | synthetic_fixture | 🧪 fixture | AVAILABLE | 3 | 0 |
| BLS Employment Projections | US | 1 | 2025-2035 | official_local | ✅ yes | AVAILABLE | 2,493 | 0 |
| Cedefop Short-Term Analytical System (STAS) | EU | 1 | Jan 2026 | — | no | LOCAL FILE FOUND | 0 | 0 |

## Narrative / Methodology

| Source | Region | Auth | Version | Origin | Prod-ready | Lifecycle | Records | Chunks |
|---|---|---|---|---|---|---|---|---|
| ESCO Handbook (methodology) | EU | 1 | Sept 2017 | authorised_manual | no | AVAILABLE | 0 | 239 |
| Future of Jobs Report | global | 3 | 2025 | authorised_manual | no | AVAILABLE | 0 | 1,088 |

## Specialist Profession Packs

| Source | Region | Auth | Version | Origin | Prod-ready | Lifecycle | Records | Chunks |
|---|---|---|---|---|---|---|---|---|
| NICE Workforce Framework for Cybersecurity | US | 1 | v2.2.0 | official_local | ✅ yes | AVAILABLE | 2,252 | 99 |
| UK HR Success Profile Guides | UK | 2 | v0e | authorised_manual | ✅ yes | AVAILABLE | 0 | 101 |

## Storage routing

- **Structured stores (SQLite)** — roles.db (incl. education/training/experience/outlook attributes), competencies.db, compensation.db, labour_market.db, credentials.db.
- **Vector store (Chroma)** — narrative/methodology PDFs only.
- Structured tables are never vectorised; narrative is never forced into tables.

See `docs/source_licensing.md`, `docs/local_source_inventory.md`, `docs/local_source_report.md`.
