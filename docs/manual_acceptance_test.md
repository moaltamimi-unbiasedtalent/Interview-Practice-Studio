# Interview OS Coach — Manual Acceptance Test

Status legend: **PASS** (verified — automated test and/or in-app check),
**NOT TESTED** (requires live credentials or a manual browser session not run
here), **FAIL** (defect). 80 checks.

> Automated coverage: full suite **959 passed, 1 skipped**; all six routes boot
> via AppTest; offline performance measured (`docs/performance_report.md`).
> Live-provider paths (real LLM answers, Google Speech, Gemini Live) need
> credentials and are marked NOT TESTED here.

## Home & navigation
1. App starts with one command / one URL (`streamlit run app.py`) — PASS
2. Home shows title, tagline, two pathway cards — PASS
3. Home shows "Prepare → Practise" journey callout — PASS
4. Home shows UNDERSTAND→PREPARE→PRACTISE→REVIEW→IMPROVE — PASS
5. Grouped sidebar nav (Prepare/Practise/Resources/Advanced) — PASS
6. "Prepare for a role" routes to Career Intelligence — PASS
7. "Start practising" routes to Interview Practice — PASS
8. Navigation preserves session state across pages — PASS

## Career Intelligence — chat & routing
9. Career page renders with header + Chat/Career Tools sections — PASS
10. Starter prompts appear on an empty chat — PASS
11. Progress states show (Understanding→…→Preparing) — PASS
12. Router classifies role queries → structured_role — PASS
13. Router classifies compensation queries → compensation — PASS
14. Router classifies trend queries → forecast — PASS
15. Router classifies mixed queries → mixed — PASS
16. Router default → vector — PASS
17. Grounded answer with citations (live model) — NOT TESTED
18. Empty KB → "insufficient evidence", no fabrication — PASS

## Structured role retrieval
19. Exact title resolves to occupation — PASS
20. Alternate title resolves to occupation — PASS
21. Occupation code lookup — PASS
22. Related occupation lookup — PASS
23. Skill lookup — PASS
24. Task lookup — PASS
25. Crosswalk/mapping (ESCO→ISCO) — PASS
26. Source provenance preserved — PASS
27. Missing role code handled safely — PASS
28. Duplicate aliases do not crash — PASS

## Compensation retrieval
29. Correct country filter — PASS
30. Correct year filter — PASS
31. Correct currency preserved — PASS
32. Correct statistic type preserved — PASS
33. Pay period preserved (annual/monthly/hourly) — PASS
34. Source provenance preserved — PASS
35. Wrong geography not scored correct — PASS
36. Wrong year not scored correct — PASS
37. Missing currency handled safely — PASS
38. Countries never merged as comparable — PASS

## Mixed routing & sources
39. Mixed role+compensation routes to mixed — PASS
40. Source types clearly separated in the report — PASS
41. Authority level shown as metadata (not truth score) — PASS

## Tools (LangChain)
42. Job Description Analyzer returns structured requirements — PASS
43. Gap Analyzer computes deterministic match % — PASS
44. Preparation Plan computes deterministic hours — PASS
45. Interview Question Generator returns categories — PASS
46. Only registered tools can run (no arbitrary exec) — PASS
47. Tool execution records are safe (no raw JD/CV) — PASS
48. "Tools used" panel renders — PASS

## RAG Inspector
49. Shows original query — PASS
50. Shows translated + alternate queries — PASS
51. Shows metadata filters — PASS
52. Shows vector hits — PASS
53. Shows keyword hits — PASS
54. Shows fused ranking — PASS
55. Shows retrieval lane (router) — PASS
56. Shows citations — PASS
57. Shows tools called — PASS
58. Never exposes system prompt / chain-of-thought — PASS

## Practise this role (handoff)
59. "Practise this role" appears after analysis — PASS
60. Builds PreparationContext from existing outputs (no extra LLM) — PASS
61. Navigates to Interview Practice — PASS
62. Pre-fills setup (editable), never auto-starts — PASS
63. "Prepared with Career Intelligence" provenance shown — PASS
64. "Return to preparation" preserves context — PASS
65. Interview reset does not erase Career context — PASS

## Interview Practice
66. Setup form renders and validates — PASS
67. Strategy generation (live model) — NOT TESTED
68. Dynamic questions + evaluation (live model) — NOT TESTED
69. Interview Deep Dive (live model) — NOT TESTED
70. Final report with JSON/Markdown export — PASS (render/seeded)
71. Text mode available — PASS
72. Record mode degrades to text without Google creds — PASS (fallback)
73. Live mode degrades to voice/text without Gemini — PASS (fallback)
74. No completed interview data lost on fallback — PASS

## Cost, export, evaluation, security, accessibility
75. Usage & diagnostics panel (hidden by default) — PASS
76. Career cost shows "unavailable" (never fabricated) — PASS
77. Career conversation export (JSON/CSV) + combined — PASS
78. Evaluation page shows baseline (11R) + expanded (11R-A) — PASS
79. Injection in query/JD/candidate/chunk stays untrusted data — PASS
80. Accessibility: headings, labelled controls, no overflow — PASS (desktop/900px; full audit NOT TESTED)
