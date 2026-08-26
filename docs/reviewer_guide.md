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
lane (role / skill / compensation / forecast / mixed) from the question; the LLM
is only consulted when the rules are ambiguous.

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
Practice — no framework objects cross the boundary.

**Why combine the two products?** So preparation flows straight into practice:
understand the role, then rehearse for it, in one place.

**How was RAG evaluated?** Phase 11R measured vector/keyword/hybrid retrieval
(Hit@K, MRR, Recall@K), tool selection and citation validity on a labelled
dataset.

**What changed after 11R-A?** New lanes were measured: routing accuracy,
structured-role retrieval, compensation correctness and provenance. Core
retrieval metrics were unchanged (the expansion adds lanes; it doesn't alter
narrative retrieval).

**What are the limitations?** Synthetic sample data (so numbers are illustrative),
a lexical offline embedder (semantic quality needs an OpenAI key), best-effort
injection defence, and live LLM/speech/live paths that need credentials.
