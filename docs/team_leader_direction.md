# Team Leader Direction — how the pieces fit

A short explanation of how the sprint work relates to the wider product.

- **Career Intelligence started as the sprint project.** It is the "Building
  Applications with AI" deliverable: LangChain + RAG + embeddings + vector/hybrid
  retrieval + query translation + structured retrieval + tool calling + domain
  security, in Streamlit over OpenRouter.
- **Interview Practice existed previously.** It is a separate, earlier interview
  simulator (setup, strategy, dynamic questions, evaluation, Deep Dive, report,
  voice/live). It was **not** built in this sprint.
- **They were unified as Interview OS Coach.** One Streamlit app, one URL, clear
  module boundaries, a shared core for infrastructure, and an integration layer
  (`PreparationContext`) connecting them.
- **Career Intelligence remains the evaluated sprint module.** It stays a
  cohesive, independently testable package with its own tests and evaluation, so
  it can be reviewed on its own merits.
- **The wider platform gives the sprint work a real use case.** Career
  Intelligence's output (role understanding + gaps + plan) feeds directly into
  Interview Practice via "Practise this role" — preparation → practice.
- **OS-4A expanded knowledge coverage.** Career Intelligence evolved from
  vector-only RAG into a multi-source architecture: a structured role database
  (ESCO/O*NET/ISCO/KldB), narrative vector knowledge, and a compensation database
  (OEWS/ASHE/Eurostat/Entgeltatlas), behind a retrieval router — everything with
  provenance and source authority.
- **11R-A evaluated the new architecture.** The 11R benchmark was preserved as
  the baseline; 11R-A measured routing accuracy, structured-role retrieval,
  compensation correctness and provenance. Core retrieval was unchanged
  (Δ = 0) — the expansion adds lanes and coverage, not a change to narrative RAG.

For the requirement map see [assignment_traceability.md](assignment_traceability.md);
for a walkthrough see [demo_script.md](demo_script.md).
