# Final Local Source Report

Measured values only — every number is a real count from the loaded stores or the inventory. Regenerate with `python scripts/final_source_report.py`.

## Counts

| Metric | Value |
|---|---|
| Files discovered in data/raw | 195 |
| Files mapped to known sources | 194 |
| Unresolved files | 1 |
| Configured sources | 26 |
| Sources found locally | 19 |
| Sources normalised (records>0) | 17 |
| Sources indexed (vector chunks>0) | 11 |
| Sources retrieval-ready | 24 |
| Structured occupation records | 7,204 |
| Task records | 22,339 |
| Skill relationships | 111,455 |
| Technology relationships | 11,572 |
| Knowledge records | 6,968 |
| Activity records | 20,141 |
| Occupation relationships | 12,016 |
| Competency records | 2,261 |
| Role-behaviour records | 5 |
| Qualification records | 3 |
| Compensation records | 1,920 |
| Labour-market records | 1,669 |
| Vector documents (narrative files indexed) | 16 |
| Vector chunks | 3,528 |
| Manual acquisition still outstanding | 2 |
| Licence review still outstanding | 2 |
| Configured but not found locally | 2 |

## Configured but not found locally

- `ba_entgeltatlas` — Entgeltatlas (acquisition: manual)
- `berufenet` — BERUFENET occupation information (acquisition: manual)

## Recommended sources still missing

- BLS Occupational Outlook Handbook structured export (US outlook + entry education)
- BERUFENET authorised export (German occupation detail beyond KldB)
- BA Entgeltatlas authorised export (German compensation)
