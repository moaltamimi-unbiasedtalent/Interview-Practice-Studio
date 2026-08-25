# Knowledge base — raw source documents

Place the curated career/labour-market source documents here. They are **not
committed** (see `.gitignore`) because they may be large or licensed; only this
README and the folder structure are tracked.

## How to add documents

1. Drop files into a **category subfolder** so their `document_type` is inferred
   from the folder name:

   ```
   data/raw/labour_market/       → document_type = labour_market
   data/raw/occupation/          → document_type = occupation
   data/raw/skills/              → document_type = skills
   data/raw/career_guidance/     → document_type = career_guidance
   data/raw/interview_guidance/  → document_type = interview_guidance
   data/raw/industry_report/     → document_type = industry_report
   ```

   Files placed directly in `data/raw/` get `document_type = uncategorized`.

2. Supported formats: **PDF, TXT, Markdown (.md), CSV**.

3. (Optional) Add a sidecar `<filename>.meta.json` next to a file to set
   `title`, `year` and `topic`, e.g.:

   ```json
   { "title": "Future of Jobs Report", "year": 2023, "topic": "labour market" }
   ```

4. For **CSV**, configure which columns become the document text and which become
   metadata when running ingestion (see `scripts/ingest.py --help`).

5. Run ingestion:

   ```bash
   python scripts/ingest.py            # discover, load, clean, chunk, report
   ```

## Suggested sources (add yourself — do not fabricate data)

- **World Economic Forum** — Future of Jobs reports (labour_market / industry_report)
- **ESCO** — European skills/competences/occupations (skills / occupation)
- **O*NET** — occupation profiles (occupation / skills)
- Official national labour-market statistics offices (labour_market)
- Reputable, redistributable career frameworks and interview guides
  (career_guidance / interview_guidance)

Only add documents you have the right to use. Record provenance in the sidecar
metadata where possible.
