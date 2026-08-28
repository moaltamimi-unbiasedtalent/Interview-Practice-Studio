# Final Local Source Report

Measured values only — every number is a real count from the loaded stores or the inventory. Regenerate with `python scripts/final_source_report.py`.

## Counts

| Metric | Value |
|---|---|
| Files discovered in data/raw | 190 |
| Files mapped to known sources | 190 |
| Unresolved files | 0 |
| Configured sources | 25 |
| Sources found locally | 16 |
| Sources normalised (records>0) | 15 |
| Sources indexed (vector chunks>0) | 10 |
| Sources retrieval-ready | 22 |
| Structured occupation records | 6,861 |
| Task records | 22,339 |
| Skill relationships | 111,455 |
| Technology relationships | 11,572 |
| Knowledge records | 6,968 |
| Activity records | 20,141 |
| Occupation relationships | 12,016 |
| Competency records | 14 |
| Role-behaviour records | 5 |
| Qualification records | 3 |
| Compensation records | 1,920 |
| Labour-market records | 7 |
| Vector documents (narrative files indexed) | 15 |
| Vector chunks | 3,066 |
| Manual acquisition still outstanding | 2 |
| Licence review still outstanding | 2 |
| Configured but not found locally | 3 |

## Configured but not found locally

- `ba_entgeltatlas` — Entgeltatlas (acquisition: manual)
- `berufenet` — BERUFENET occupation information (acquisition: manual)
- `bls_ooh` — Occupational Outlook Handbook (OOH) (acquisition: auto-download)

## Recommended sources still missing

- BLS Occupational Outlook Handbook structured export (US outlook + entry education)
- BERUFENET authorised export (German occupation detail beyond KldB)
- BA Entgeltatlas authorised export (German compensation)
