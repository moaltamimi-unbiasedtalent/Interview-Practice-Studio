# Security classifier evaluation

Dataset: 12 labelled prompts (benign + injection).

| Metric | A: deterministic | B: deterministic + classifier |
|---|---|---|
| True positives | 5 | 5 |
| False positives | 0 | 0 |
| False negatives | 0 | 0 |
| True negatives | 7 | 7 |
| Latency / item (ms) | 0.0146 | 0.0098 |
| Cost | N/A (offline stub; a real classifier adds per-call API cost) | N/A (offline stub; a real classifier adds per-call API cost) |

## Recommendation

Retain the deterministic guard as the primary defence. On this set it already catches the obvious attacks at ~zero latency and zero cost. The secondary classifier only changes outcomes on ambiguous cases; before adding it to the production flow, evaluate a real moderation API's true/false-positive rates, latency and cost with the manual live suite. Only adopt it if it reduces false negatives without materially raising false positives or latency.
