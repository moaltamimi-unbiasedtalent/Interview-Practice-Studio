# Architecture — RAG + Tool Orchestration

Phase 7 combines advanced RAG and domain tool calling into **one explainable,
non-autonomous** LangChain workflow behind a single domain service,
`CareerIntelligenceService`. The Streamlit layer calls the service; it never wires
retrieval, translation and tools itself.

## End-to-end flow

```
                          ┌──────────────────────────────────────────┐
User (Streamlit)  ───────▶│         CareerIntelligenceService        │
                          │            (src/copilot/service.py)       │
                          └──────────────────────────────────────────┘
   1. Input validation            (length / empty guard)
   2. Intent understanding  ─────▶ QueryTranslator            rag/translation.py
   3. Query translation           (rewrite, multi-query, safe filters)
   4. Retrieval requirement ─────▶ route_for_intent           rag/routing.py
   5. Hybrid retrieval      ─────▶ Hybrid (vector + BM25) + RRF   retrieval/*
   6. Tool requirement      ─────▶ route.tools ∩ available inputs
   7. Tool execution        ─────▶ ToolInvoker (registered tools) tools/*
   8. Bounded context       ─────▶ trust-separated blocks      rag/synthesis.py
   9. OpenRouter            ─────▶ LangChain ChatOpenAI        llm/openrouter.py
  10. Grounded response           (answer + citations + tools used)
```

Compact view required by the brief:

```
LangChain → query translation → RAG → tools → answer
```

Every stage has a **controlled fallback**: a failure degrades the result and is
recorded in `PipelineTrace` — it never crashes the Streamlit session.

## Intent routing (RAG? tool? both? neither?)

`route_for_intent` (deterministic table — the model never decides the route):

| Intent | RAG | Tools |
| ------ | --- | ----- |
| factual_career / role_research / skill_research | ✅ | — |
| job_description_analysis | ❌ | Job Analyzer |
| candidate_comparison | ✅ | Job Analyzer → Gap Analyzer |
| preparation_planning | ✅ | Job Analyzer → Gap Analyzer → Prep Planner |
| interview_preparation | ✅ | Question Generator |
| smalltalk | ❌ | — |

A planned tool only runs if its inputs are present (a JD, a candidate background,
a timeframe); otherwise it is skipped with a note.

## Three worked patterns

- **Pure RAG** — *"What does the evidence say about AI skill demand?"* → retrieve
  + cite; no tools.
- **Pure tool** — *"Analyse this job description."* → Job Analyzer only; no RAG.
- **Combined** — *"Compare my background with this role and tell me which skills
  are becoming more important in the labour market."* → Job Analyzer → Gap
  Analyzer (deterministic stats) + RAG evidence on labour-market skills → grounded
  synthesis.

## Context trust boundaries

The final prompt keeps trust zones in **separate labelled blocks** (see
`rag/synthesis.py`), never concatenated into one undifferentiated string:

| Zone | Trust | Block |
| ---- | ----- | ----- |
| System instructions | trusted | system message |
| User question | user | `[USER QUESTION]` |
| Job description | untrusted data | `[JOB DESCRIPTION]` |
| Candidate context | untrusted data | `[CANDIDATE CONTEXT]` |
| Tool outputs | trusted computation | `[TOOL RESULTS]` |
| Retrieved documents | untrusted data | `[RETRIEVED EVIDENCE]` (cited) |

The model is told the data blocks are never instructions (prompt-injection
isolation) and must label its answer's **Evidence (from sources)** `[n]`, **Tool
results (calculated)**, and **Recommendation** distinctly. It never fabricates
citations and says so explicitly when evidence is insufficient.

## Failure recovery

| Failure | Recovery |
| ------- | -------- |
| Query-translation failure | heuristic translation (`strategy=heuristic`), marked degraded |
| Empty retrieval | continues; answer states evidence is insufficient |
| Vector failure | hybrid degrades to BM25-only; marked degraded |
| BM25 failure | hybrid degrades to vector-only; marked degraded |
| Tool failure | recorded as a `ToolExecution(status=error)`; pipeline continues |
| Structured-output failure | surfaced as a tool error; pipeline continues |
| OpenRouter failure | deterministic limited-summary fallback answer |

None raise into Streamlit — each is caught and noted in the trace.

## RAG Inspector (safe pipeline visibility)

For the last query the inspector shows: intent, rewritten + alternative queries,
metadata filters, RAG-required/used, tool decision and tools invoked, vector
hits, keyword hits, fused hybrid ranking, final evidence sources, degraded stages
and notes, and the exact context sent to the model. It never exposes system
prompts or hidden reasoning.

## Requirement mapping

| Sprint requirement | Where |
| ------------------ | ----- |
| **Advanced RAG** (embeddings, hybrid, query translation, grounding, citations) | `embeddings.py`, `vectorstore.py`, `retrieval/*`, `rag/translation.py`, `rag/context.py`, orchestrated in `service.py` |
| **Tool Calling** (≥3 domain tools via LangChain) | `tools/*`, dispatched in `service.py` |
| **LangChain** | `llm/openrouter.py` (ChatOpenAI over OpenRouter), tool binding, structured output |
| Domain service (not in `app.py`) | `service.py`; `copilot_app.py` only calls it |

See also [`docs/rag.md`](rag.md), [`docs/query_translation.md`](query_translation.md),
[`docs/hybrid_search.md`](hybrid_search.md), [`docs/tool_calling.md`](tool_calling.md).

## Tests

[`tests/test_copilot_orchestration.py`](../tests/test_copilot_orchestration.py)
covers mocked end-to-end scenarios A–J: pure RAG, pure tool, RAG + tool, multiple
tools, insufficient evidence, translation failure, tool failure, empty vector DB,
hybrid degradation, and invalid structured output. No paid API calls — every LLM
boundary is an injected fake.
