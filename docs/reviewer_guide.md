# Reviewer Guide — Career Intelligence in plain language

Short, plain answers to the concepts a reviewer may ask about. (No step-by-step
model reasoning — just what each thing is and why it's here.)

**What is RAG?** Retrieval-Augmented Generation: before answering, the app
*retrieves* relevant evidence from a knowledge base and gives it to the model, so
answers are grounded in real sources instead of the model's memory.

**What is an embedding?** A numeric vector that represents the meaning of a piece
of text, so texts with similar meaning have nearby vectors.

**Why chunk documents?** Long documents are split into small passages so
retrieval returns the specific relevant part, and so each fits the model's
context window.

**What is similarity search?** Finding the chunks whose embeddings are closest to
the query's embedding (here, cosine similarity).

**What is query translation?** Rewriting a vague user question into a clearer
retrieval query, and generating a few alternate phrasings — without adding facts.

**Why multi-query?** One phrasing can miss relevant chunks; several phrasings
cover more angles, and the results are merged.

**What is BM25?** A classic keyword-ranking algorithm that scores exact term
overlap — great for precise tokens like "Python", "SAP", "ISO 27001".

**Why hybrid search?** Combine semantic (vector) recall with exact-term (BM25)
precision, so both conceptual and exact-token questions work.

**Why structured retrieval?** Some questions want a list from a taxonomy (a
role's skills) or a table row (a salary figure), not the nearest prose — so those
go to structured databases, not vectors.

**Why not put everything in Chroma?** Structured facts lose their structure as
text chunks and become easy to misquote; occupations/skills are relational and
compensation is tabular. Only narrative belongs in the vector store.

**What is LangChain doing?** It provides the chat-model wrapper over OpenRouter,
the tool-calling plumbing, and structured-output parsing.

**Why use OpenRouter?** One OpenAI-compatible endpoint that routes to approved
models, so the code stays provider-neutral and keys live in one place.

**What is tool calling?** Letting the model invoke specific, registered functions
(here: job analysis, gap analysis, plan, questions) with validated arguments.

**How does the tool router work?** A deterministic classifier picks the retrieval
lane from the question; the LLM is only consulted when the rules are ambiguous.
Lanes: role, skill, compensation, forecast, mixed, plus competency (DigComp),
cybersecurity (NICE work roles), shortage, openings, transition, and seniority.
It also detects the country and prefers national official sources for
country-specific questions (e.g. Germany → KldB/Entgeltatlas before ESCO).

**Do the structured stores actually answer the chat?** Yes. The router's lane
drives a *retrieval coordinator* that queries the right SQLite store (roles,
compensation, competency, labour-market), resolves the occupation from the
question (handling aliases like HRBP → HR Business Partner), applies the country
precedence, and returns typed evidence. That evidence is merged with the vector
(RAG) results into separated sections the model must cite — so a salary answer
comes from the compensation store and is cited to, say, "BLS OEWS — … — US —
2025", not from the model's memory.

**What if the data isn't there?** For a factual question with no matching record
(e.g. a salary for a country we don't hold), the app says so plainly and may offer
clearly-labelled evidence from another geography — it does not fall back to guessed
numbers.

**Why are the structured stores "now actually used"?** Earlier phases classified
the lane but the chat still answered from vector RAG only. Now the router's lane
drives a retrieval coordinator that queries the real SQLite stores and merges that
typed, cited evidence with vector results — so a role/salary/shortage answer comes
from the store, not the model's memory.

**How is a salary query answered?** "What does an HR manager earn in the US?" →
router picks the `compensation` lane → the occupation is resolved (HR manager →
Human Resources Managers) → the country is detected (US) → the compensation store
is queried with US preferred → the median/period/currency/year record is returned
and cited (e.g. "BLS OEWS — Human Resources Managers — US — 2025"). No record for
the country → it says so and may show another geography, clearly labelled.

**How does geographic source precedence work?** Each country maps to an ordered
list of preferred sources (e.g. Germany → KldB/BERUFENET/Entgeltatlas before ESCO;
US → O*NET/BLS; UK → ONS/Civil Service). Country-specific official statistics
outrank generic international ones for country-specific questions.

**How is current demand different from forecasts?** They are kept as separate
signals, never blended into one "demand score": long-term **forecast** (Cedefop /
BLS Employment Projections), structural **shortage** (Cedefop CLSSI), and
near-real-time **vacancy rate** (Eurostat JVS, country-level, flagged
experimental). A "right now" question uses vacancy data; a "will it grow" question
uses the forecast.

**How do you tell real data from test fixtures?** Every source carries a
`data_origin` (official_local / official_download / authorised_manual /
api_snapshot / synthetic_fixture) and a `production_ready` flag. A source is
production-ready only when it is available, its data is real (not a fixture), and
its licence is clear. The Knowledge Base shows two counts — *retrieval-ready*
(anything loaded) and *production-ready (real)* — and badges each source REAL DATA
or FIXTURE DATA. So a small hand-authored sample can never masquerade as loaded
official data. Loaders also refuse to run without an explicit `--source` or
`--fixtures`, so fixture use is always deliberate.

**How do you know a source is really loaded?** Each source has a *measured*
lifecycle in `data/source_status.json` derived from what is on disk — a source in
the manifest is "configured", not "available", until its records are actually
loaded. The Knowledge Base page shows this honestly (CONFIGURED / MANUAL
ACQUISITION / LICENCE REVIEW / AVAILABLE), so nothing is implied to exist that
doesn't.

**Why are calculations deterministic?** Match percentages and study-hour
allocations are computed in Python from explicit rules — the model never invents
a score or does hidden arithmetic.

**How do citations work?** Retrieved passages are numbered; the model cites `[n]`;
only markers that map to a real retrieved chunk are shown.

**What happens when there is no evidence?** The app says so explicitly ("not
enough evidence") rather than making something up.

**What is prompt injection?** Malicious text (e.g. inside a job description or a
retrieved document) that tries to override the app's instructions.

**Why are retrieved documents untrusted?** They come from outside; they're placed
in clearly labelled data blocks and never treated as instructions, and injected
chunks are excluded.

**What is PreparationContext?** A small, plain-data contract that carries the
role, requirements, gaps and sources from Career Intelligence to Interview
Practice — no framework objects cross the boundary. It can also carry a **safe,
summarised company context** (never raw files).

**How does company context work?** A candidate supplies an employer's official
URL / careers page and/or uploads company materials (annual report, investor
deck). `build_company_context` validates the URLs, classifies each source
(official / careers / investor relations / annual report / filing / press
release), scans every document for prompt injection (attack text is dropped),
extracts publication dates, and stamps `retrieved_at` — company facts are
time-sensitive and are **kept out of the permanent occupational knowledge base**.
It never invents company news: recent updates come only from dated lines in the
supplied material. The summary is added to the answer as clearly-labelled
`[COMPANY CONTEXT]` data (never treated as an occupational fact or as
instructions). Live web search is optional and behind a provider interface — the
sprint default fetches nothing.

**Why combine the two products?** So preparation flows straight into practice:
understand the role, then rehearse for it, in one place.

**How was RAG evaluated?** Phase 11R measured vector/keyword/hybrid retrieval
(Hit@K, MRR, Recall@K), tool selection and citation validity on a labelled
dataset.

**What changed after 11R-A?** New lanes were measured: routing accuracy,
structured-role retrieval, compensation correctness and provenance. Core
retrieval metrics were unchanged (the expansion adds lanes; it doesn't alter
narrative retrieval).

**What changed in KB-2?** The knowledge foundation was expanded to 25
authoritative sources across five stores (role, competency, compensation,
labour-market, vector), each kept in the right store for its data type, with a
measured source lifecycle, geographic source precedence, and new routing lanes.
`scripts/eval_knowledge_expansion.py` measures routing (1.0), geographic
precedence (1.0) and coverage — without touching the 11R / 11R-A baseline.

**What are the limitations?** Synthetic sample data (so numbers are illustrative),
a lexical offline embedder (semantic quality needs an OpenAI key), best-effort
injection defence, and live LLM/speech/live paths that need credentials.
