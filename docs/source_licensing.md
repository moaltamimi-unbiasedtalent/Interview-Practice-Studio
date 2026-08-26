# Source Licensing

Derived from [data/source_manifest.json](../data/source_manifest.json). Licence
terms are **not guessed**: where a source's reuse terms are not confirmed, it is
marked *review required* and treated as non-redistributable. **No datasets are
committed to this repository** — everything is acquired locally (see
[rebuild_knowledge_base.md](rebuild_knowledge_base.md)).

| Source | Publisher | Use | Licence | Committed? | Acquisition | Redistribution |
| --- | --- | --- | --- | --- | --- | --- |
| O*NET | US DOL | occupations/skills (structured) | CC BY 4.0 | No | auto-download | allowed w/ attribution |
| ESCO | European Commission | occupations/skills (structured) | review required | No | manual (portal) | not until confirmed |
| ISCO-08 | ILO | occupation hierarchy (structured) | review required | No | manual | not until confirmed |
| KldB 2010 | Bundesagentur für Arbeit | occupations (structured) | review required | No | manual | not until confirmed |
| OEWS | US BLS | compensation (structured) | Public domain (US gov work) | No | auto-download | allowed |
| ASHE | UK ONS | compensation (structured) | Open Government Licence v3.0 | No | auto-download | allowed w/ attribution |
| Eurostat earnings | Eurostat | compensation (structured) | CC BY 4.0 | No | auto-download | allowed w/ attribution |
| Entgeltatlas | Bundesagentur für Arbeit | compensation (structured) | review required | No | manual (portal) | not until confirmed |
| Cedefop Skills Forecast | Cedefop | labour-market forecast (vector) | review required | No | manual | not until confirmed |
| EQF | European Commission | competency framework (vector) | review required | No | manual | not until confirmed |
| Future of Jobs | World Economic Forum | industry report (vector) | review required | No | manual | not until confirmed |

Notes:

- "auto-download" = the manifest marks it directly downloadable and not licence-
  blocked; `scripts/download_sources.py` will fetch only these.
- "manual" = `manual_acquisition_required: true` (portal, registration or licence
  review); these are never scraped.
- We do **not** scrape LinkedIn, Glassdoor, Indeed, Levels.fyi, proprietary
  salary sites or paid consultant reports.
- The committed synthetic corpus (`evaluations/corpus/`) and knowledge samples
  (`evaluations/knowledge_samples/`) are **not** any of the above datasets — they
  are small, general, hand-authored files for a runnable, reproducible demo.
- Always confirm a source's current licence with its publisher before
  redistributing anything derived from it.
