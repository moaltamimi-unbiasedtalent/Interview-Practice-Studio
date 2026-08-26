# Interview OS — Performance Report

Representative latencies for the Career Intelligence lanes, measured offline (local hashing embedder, heuristic translator, fake model) so they are reproducible and free. Micro-stages: 200 iterations; full pipeline: 50. These are machine-dependent measurements, **not** targets.

## Career stages

| Stage | Mean (ms) | Median (ms) |
|---|---|---|
| intent/router | 0.003 | 0.002 |
| query translation (heuristic) | 0.002 | 0.002 |
| structured role retrieval | 0.01 | 0.009 |
| vector retrieval | 0.548 | 0.537 |
| hybrid retrieval | 0.56 | 0.558 |
| compensation lookup | 0.01 | 0.009 |
| tool: gap analyzer (deterministic) | 0.007 | 0.007 |
| tool: preparation plan (deterministic) | 0.005 | 0.005 |
| service.answer pipeline (excl. live model) | 0.124 | 0.117 |

## Not measured offline (require a live provider)

- **Career final answer (real LLM synthesis)** — dominated by the OpenRouter model round-trip; the pipeline row above excludes it (fake model).
- **Interview**: question generation, answer evaluation, Deep Dive — each is a live OpenRouter call.
- **Speech transcription** and **Gemini Live** — require Google credentials.

These are excluded rather than estimated; measure them in a live session.

## Cost

- **Career LLM**: OpenRouter via LangChain — token usage tracked; provider cost is not surfaced on this path, so cost shows **unavailable** (never fabricated).
- **Interview LLM**: OpenRouter via HTTPX — `PricingService` reports reported→calculated→none cost.
- **Speech / Live**: usage not billed through the app; **unavailable** here.
- Career and Interview usage are tracked separately (no merged totals).
