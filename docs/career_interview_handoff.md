# Career → Interview Handoff ("Practise this role")

The handoff is what makes Interview OS Coach one product rather than two apps
behind a menu: Career Intelligence turns its analysis into a structured
`PreparationContext` and hands it to Interview Practice to pre-fill a setup the
candidate reviews and edits.

```
Career Intelligence
      │  (Job Description Analyzer, Gap Analyzer, RAG evidence)
      ▼
PreparationContext              src/integration/models.py   (plain Pydantic)
      │  store in session state + navigate
      ▼
Interview Practice              pre-filled setup (editable) → strategy → practice
```

## The contract — `PreparationContext`

[`src/integration/models.py`](../src/integration/models.py). Plain domain data
only — **no** Chroma objects, LangChain documents, retriever internals or
OpenRouter objects — so it is safe to hold in session state and hand across the
boundary. Optional fields stay optional; the producer never invents data.

Fields: `target_role` (required), `industry`, `company_context`,
`job_description`, `seniority`, `required_skills`, `key_responsibilities`,
`leadership_expectations`, `candidate_strengths`, `candidate_gaps`,
`likely_interview_topics`, `priority_competencies`, `source_references`
(provenance).

## Producer (Career side)

[`src/integration/preparation_context.py`](../src/integration/preparation_context.py)
assembles the context from **existing** structured outputs — the Job Description
Analyzer's `RoleRequirements`, the deterministic Gap Analyzer's
`GapAnalysisResult`, and retrieved evidence's citations. It makes **no extra LLM
call**: it only reshapes data that already exists. `priority_competencies` puts
high-severity gaps first, then required skills.

The **Career Tools** page shows a **Practise this role** section once a role has
been analysed, with a short preview (role, seniority, top competencies, priority
gaps, likely interview themes).

### Target role is mandatory

A `PreparationContext` **must** have a `target_role`; it is never fabricated (no
"Unknown"/"N/A" placeholder). Resolution is deterministic
(`_resolve_handoff_target_role`): the analyser's `role_title` is used when
present; otherwise the user confirms/edits the role in a **Target role** field
(`handoff_target_role`). Only when a non-empty role exists does the UI build the
context — so an analyser response without a `role_title` shows a "Target role
needed" prompt instead of crashing, and the handoff button stays disabled until a
role is provided. The handoff still **never** starts an interview automatically.
Analysing a **new** job description clears the stale downstream Career Tool state
(gap, plan, questions, confirmed role, active context) so it cannot leak into the
new role's handoff; unrelated Career chat/history is preserved.

## Handoff (navigation + state)

[`src/integration/handoff.py`](../src/integration/handoff.py) owns the session
contract. Clicking **Practise this role**:

1. stores the `PreparationContext` under a namespaced session key;
2. queues navigation to Interview Practice (the shell's `_pending_nav` flag);
3. pre-populates the interview setup;
4. lets the candidate review/edit everything;
5. **never** starts an interview automatically.

## Consumer (Interview side)

The interview setup reads the context through the adapter only —
`handoff.interview_prefill(session_state)` returns **plain data** (defaults +
generic taxonomy ids). Interview Practice never imports Career retrievers,
LangChain chains, Chroma or tool internals. Prefill maps: role, industry,
seniority → career level, company context, job description, and a background
composed from strengths + development areas; seniority also suggests a difficulty.
All values are defaults the candidate can change.

### Targeting (balanced)

Because the full job description and a background covering **both** strengths and
gaps are pre-filled, the existing strategy/question generation naturally focuses
on likely themes, priority competencies and an appropriate challenge level.
Candidate gaps influence what is practised, but the interview stays balanced — it
does not generate only weakness-probing questions.

### Provenance

`source_references` is preserved and the interview shows *"Preparation informed
by Career Intelligence — N source(s)"*. This is grounding provenance, **not**
scoring evidence — interview scores remain practice feedback, never a hiring
decision.

## Reverse navigation

After the readiness report, **Return to preparation** navigates back to Career
Intelligence with the context intact.

## Session boundaries

- The stored context changes only on the explicit **Practise this role** action;
  running new analysis does not silently overwrite it.
- **Clear preparation context** (Career sidebar) removes it on demand; a new
  Career session can clear it.
- Resetting the interview clears only the interview's own namespaced state — the
  Career context survives.
- Normal Streamlit reruns preserve the handoff (it lives in session state).

## Tests

[`tests/test_integration_handoff.py`](../tests/test_integration_handoff.py):
context generation, partial/missing fields, store/get/clear state, navigation,
setup pre-population + seniority mapping, session boundaries, JSON-serialisable
purity (no raw career objects), provenance, and a subprocess check that importing
the handoff pulls no retrievers/chains/Chroma or the interview module.
