# Model-setting comparison

**Status:** pending

## Method

Temperature and the token limit are swept while the model and prompt technique stay constant, so their effects can be compared in isolation.

- **Model:** `openai/gpt-5-mini`
- **Prompt technique:** rubric_json
- **Temperatures:** [0.1, 0.5, 0.9]
- **Token settings:** concise (512), detailed (1024)
- **Temperature supported by model:** True

## Fixed scenario (profession-neutral)

- **Target role:** Project Coordinator
- **Question:** Tell me about a time you improved how your team worked.
- **Candidate answer:** I noticed our weekly updates were slow, so I suggested a shorter format. People seemed to like it and things felt a bit smoother afterwards.

## Recorded metrics

| Temp | Tokens | Valid JSON | Prompt tok | Completion tok | Cost (USD) | Latency (s) | Overall |
|---|---|---|---|---|---|---|---|
| 0.1 | concise (512) | — | — | — | — | — | — |
| 0.1 | detailed (1024) | — | — | — | — | — | — |
| 0.5 | concise (512) | — | — | — | — | — | — |
| 0.5 | detailed (1024) | — | — | — | — | — | — |
| 0.9 | concise (512) | — | — | — | — | — | — |
| 0.9 | detailed (1024) | — | — | — | — | — | — |

## Qualitative dimensions (scored manually)

| Temp | Tokens | completeness | specificity | consistency | structured output validity | Observations |
|---|---|---|---|---|---|---|
| 0.1 | concise | PENDING | PENDING | PENDING | PENDING | PENDING |
| 0.1 | detailed | PENDING | PENDING | PENDING | PENDING | PENDING |
| 0.5 | concise | PENDING | PENDING | PENDING | PENDING | PENDING |
| 0.5 | detailed | PENDING | PENDING | PENDING | PENDING | PENDING |
| 0.9 | concise | PENDING | PENDING | PENDING | PENDING | PENDING |
| 0.9 | detailed | PENDING | PENDING | PENDING | PENDING | PENDING |

## Notes
- Model and prompt technique are held constant; only temperature and the token limit vary.
- Identical input across every combination.
- Only parameters the model supports are swept (see 'temperature supported').
- Costs are USD; reported where available, otherwise estimated — not a bill.
- Completeness, specificity and consistency are scored manually after review.
