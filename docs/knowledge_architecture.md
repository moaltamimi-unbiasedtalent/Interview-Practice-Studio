# Career Intelligence — Knowledge Architecture

Career Intelligence is a **multi-source** knowledge system, not a single vector
store. A router sends each question to the lane that can actually answer it.

```
                    CAREER INTELLIGENCE
                           │
        ┌──────────────────┼───────────────────┐
   Structured Role DB   Vector Knowledge     Compensation DB
   (ESCO, O*NET,        (methodology,        (OEWS, ASHE,
    ISCO, KldB)          reports, frameworks) Eurostat, Entgeltatlas)
        └──────────────────┼───────────────────┘
                     Hybrid Router
                           ▼
                    Grounded answer (with provenance)
```

## Why not everything in Chroma

Embedding everything and hoping cosine similarity answers every question is the
wrong tool for structured facts:

- **Occupations/skills/tasks** are relational and enumerable — "what skills does
  a data analyst need?" wants a *list from a taxonomy*, not the nearest prose
  chunk. Storing a taxonomy as free-text chunks loses structure and invites
  hallucinated gaps.
- **Compensation** is tabular and context-bound (currency, period, statistic,
  geography, year). Chunked into text it becomes uncomparable and easy to
  misquote.
- **Narrative** (methodology, forecasts, competency frameworks) *is* prose and
  belongs in vector RAG.

So we keep structured data in structured stores and narrative in vectors.

## The three lanes

| Lane | Store | Sources | Good for |
| ---- | ----- | ------- | -------- |
| **Structured Role DB** | SQLite (`src/copilot/knowledge/roles.py`) | ESCO, O*NET, ISCO, KldB | role duties, tasks, skills, occupation hierarchy, transitions |
| **Vector Knowledge** | Chroma (existing RAG) | methodology, market reports, competency frameworks | conceptual / narrative questions |
| **Compensation DB** | SQLite (`compensation.py`) | OEWS, ASHE, Eurostat, Entgeltatlas | pay statistics with strict context |

## Routing

`src/copilot/knowledge/router.py` classifies questions **deterministically**
(keyword rules), consulting an LLM only when ambiguous:

| Question | Lane |
| -------- | ---- |
| "What does a Logistics Manager do?" | Structured Role DB |
| "What skills do cybersecurity analysts need?" | Structured Role DB (+ vector context) |
| "What does a Data Analyst earn in Germany?" | Compensation DB |
| "Is demand for AI roles expected to grow?" | Vector / Forecast |
| "What skills does a PM need and what do they earn in Germany?" | Mixed |

The chosen lane is shown in the **RAG Inspector**. (The baseline chat still runs
vector RAG; structured lanes are surfaced as capabilities and via the router in
this phase.)

## Provenance & authority

Every structured record and vector chunk can expose one
`Provenance` (`provenance.py`): `source_id`, `source_title`, `publisher`,
`source_type`, `authority_level`, `country`, `language`, `version`,
`reference_year`, `licence`, `source_url`, `retrieval_date`, `content_type`, plus
role-specific (`occupation_code`, `isco_code`) and compensation-specific
(`currency`, `pay_period`, `statistic`, `geography`) fields.

**Authority levels** (retrieval/ranking metadata, **not** a truth score):

- **Level 1 — official/statistical:** European Commission, ILO, O*NET, BLS,
  Bundesagentur für Arbeit, ONS, Eurostat, Cedefop, NIST.
- **Level 2 — public/professional frameworks:** Civil Service frameworks,
  DigComp, EQF.
- **Level 3 — reputable industry research.**

## Compensation handling

Compensation figures preserve, and never silently mix:

- median vs mean (`statistic_type`);
- annual vs monthly vs hourly (`pay_period`);
- currency and geography;
- reference year and provisional/final status (`sample_quality`).

The repository filters by context and **never merges different countries or
periods** as if comparable, and never implies precision beyond the source.

## Career transitions & seniority

`transitions.py` compares two occupations (shared / unique / transferable skills,
related tasks, key gaps, adjacent occupations) from structured data — it **feeds**
the Candidate Gap Analyzer rather than duplicating it. `seniority.py` describes
seniority by dimensions (autonomy, responsibility, scope, complexity, leadership,
stakeholder exposure) from public frameworks (EQF-derived, attributed) — never an
invented rule like "senior = X years".

## Licensing & acquisition

`data/source_manifest.json` registers each source with licence and acquisition
flags. **Licence terms are never invented** — uncertain ones set
`licence_review_required: true`; sources that can't be safely auto-downloaded set
`manual_acquisition_required: true`. We do **not** scrape LinkedIn/Glassdoor/
Indeed/Levels.fyi/proprietary salary sites or paid reports.

**No datasets are committed** (licensing/size). Reproduce locally:

```bash
python scripts/source_status.py        # see configured sources + flags
python scripts/download_sources.py     # fetch only auto-downloadable sources
python scripts/normalise_roles.py      # build the structured role DB
python scripts/load_compensation.py    # build the compensation DB
python scripts/rebuild_vector_index.py # re-embed narrative knowledge
```

Committed synthetic samples (`evaluations/knowledge_samples/`) let the pipeline
run end-to-end without downloads for demonstration and tests.

## Sprint relevance

This strengthens **Advanced RAG** (structured retrieval, a real domain knowledge
base, retrieval routing) and **Domain specialisation** (roles, skills,
compensation, career paths). The hard-optional **hybrid search** remains intact.
No new optional task is claimed.
