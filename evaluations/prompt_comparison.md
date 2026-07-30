# Prompt comparison

**Status:** completed

## Method

The same evaluation task is run across all five prompt techniques with identical input and identical model settings, so the only variable is the technique.

- **Model:** `openai/gpt-5-mini`
- **Temperature:** 0.3
- **Max tokens:** 1024

## Fixed scenario (profession-neutral)

- **Target role:** Project Coordinator
- **Sector:** general business
- **Career level:** mid
- **Interview type:** behavioural
- **Question:** Tell me about a time you improved how your team worked.
- **Candidate answer:** I noticed our weekly updates were slow, so I suggested a shorter format. People seemed to like it and things felt a bit smoother afterwards.

## Recorded metrics

| Technique | Valid JSON | Prompt tok | Completion tok | Cost (USD) | Latency (s) | Overall |
|---|---|---|---|---|---|---|
| Zero-shot instruction | False | — | — | — | — | — |
| Role and persona prompting | False | — | — | — | — | — |
| Few-shot prompting | False | — | — | — | — | — |
| Structured analytical procedure | False | — | — | — | — | — |
| Rubric-constrained structured output | False | — | — | — | — | — |

## Evaluation dimensions (scored manually)

For each technique, score 1–5 and add observations:

| Technique | relevance | specificity | role adaptation | structure | actionability | hallucination risk | json reliability | Observations |
|---|---|---|---|---|---|---|---|---|
| Zero-shot instruction | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Role and persona prompting | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Few-shot prompting | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Structured analytical procedure | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |
| Rubric-constrained structured output | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING |

## Notes
- Identical model, temperature and token limit across all techniques.
- Identical user input (question + candidate answer) across all techniques.
- Costs are in USD; reported where available, otherwise a calculated estimate — never a final bill.
- Do not treat the longest response as the best; judge on the evaluation dimensions.
- Manual dimensions are scored by a human after reviewing the outputs; they are not auto-generated.
