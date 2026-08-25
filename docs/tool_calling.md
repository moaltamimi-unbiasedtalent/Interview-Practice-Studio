# Domain Tool Calling

Phase 6 satisfies the sprint's **Tool Calling** core requirement: the assignment
needs at least three domain-relevant tools; the Copilot implements **four**,
through LangChain tool calling over the existing OpenRouter integration — and
never as an unrestricted autonomous agent.

> Layout note: namespaced under `src/copilot/`, so the brief's `src/tools/*` lives
> at [`src/copilot/tools/`](../src/copilot/tools).

## The four tools

| # | Tool | Kind | Module |
| - | ---- | ---- | ------ |
| 1 | Job Description Analyzer | LLM (structured output) | [`job_analyzer.py`](../src/copilot/tools/job_analyzer.py) |
| 2 | Candidate Gap Analyzer | Deterministic Python | [`gap_analyzer.py`](../src/copilot/tools/gap_analyzer.py) |
| 3 | Preparation Plan Calculator | Deterministic arithmetic | [`prep_planner.py`](../src/copilot/tools/prep_planner.py) |
| 4 | Interview Question Generator | LLM (structured output) | [`question_generator.py`](../src/copilot/tools/question_generator.py) |

### 1. Job Description Analyzer

Input: a pasted job description. Output: `RoleRequirements` — role title and
seniority *where evident*, key responsibilities, required/preferred skills,
technologies, leadership and stakeholder expectations, and likely interview
themes. It must **not invent** requirements: anything not explicitly in the JD is
placed in a separate `interpretation_notes` list, so explicit requirements and
reasonable interpretation are never conflated.

### 2. Candidate Gap Analyzer (deterministic)

Input: candidate background + `RoleRequirements`. Output: matched / partially
matched / missing requirements, strengths, prioritised gaps, and **`MatchStats`
computed in Python** from explicit token-coverage criteria (`text_match.py`):
`match_percentage = matched / total`, `weighted = (matched + 0.5·partial) /
total`. There is **no LLM-invented match score**. This is development coaching,
not a hiring decision.

### 3. Preparation Plan Calculator (deterministic)

Input: priority gaps, days until interview, hours per week. Output: total
available hours, per-gap hours weighted by severity (high 3 / medium 2 / low 1),
share percentages, a week-by-week structure, and recommended actions. **All time
allocation and arithmetic is Python** (`total = hours_per_week × days ÷ 7`); the
model performs no hidden arithmetic (action text is template-generated).

### 4. Interview Question Generator

Input: role, requirements, career-intelligence findings, retrieved evidence,
desired focus. Output: `InterviewQuestionSet` — questions grouped across
categories (behavioural, situational, competency, technical, leadership,
stakeholder, executive, culture/values), grounded in the supplied context. This
**prepares** likely questions; it does **not** run an interview simulation — that
remains the Interview Practice module's responsibility.

## Tool schemas & safety

- Every tool has an explicit Pydantic **argument schema** (`extra="forbid"`) in
  [`schemas.py`](../src/copilot/tools/schemas.py); every output is a validated
  structured model.
- Tool **descriptions** tell the model when the tool is appropriate, when it is
  not, and what each parameter means.
- The model can invoke **only** the four registered tools. `ToolInvoker` looks up
  the name in the registry and rejects anything else as `unsupported` — there is
  no path to arbitrary Python, shell, filesystem or network calls, and no
  autonomous multi-step agent loop.

## LangChain integration

```
messages ──▶ chat_model.bind_tools(build_langchain_tools(registry))
                       │  (model decides)
                       ▼
             AIMessage.tool_calls ──▶ parse_tool_calls() ──▶ ToolInvoker.invoke()
                                                                 │ validate args (Pydantic)
                                                                 │ execute registered func
                                                                 │ record ToolExecution
                                                                 ▼
                                                            ToolResult (typed)
```

`run_model_with_tools` performs one controlled pass: invoke the (tool-bound)
model, dispatch any requested calls, return the results. `StructuredTool`s are
built from the same registry so the model sees exactly the callable set.

## Tool execution records

Each call yields a safe [`ToolExecution`](../src/copilot/models.py):
`tool_name`, `status` (`ok` / `error` / `invalid_args` / `unsupported`),
`duration_seconds`, `safe_argument_summary`, `safe_result_summary`, `error`.
**Summaries never include the full candidate background or job description** —
only sizes and counts (e.g. `"job_description (1200 chars)"`, `"3 matched / 1
partial / 2 missing; match 50.0%"`), so records are safe to display and log.

## Streamlit

The **Career Tools** page runs the guided flow (analyze JD → gap analysis →
preparation plan → question generation) and shows a collapsed **Tools used**
panel listing each tool with a ✓/✗, status, duration and safe summaries. Internal
prompts and chain-of-thought are never exposed.

## Tests

[`tests/test_copilot_tools.py`](../tests/test_copilot_tools.py) covers a correct
job-analysis call, a gap-analysis call, the deterministic match calculation,
preparation-plan arithmetic, interview-question generation, the no-tool-needed
case, sequential tools, malformed arguments, a tool exception (with no leaked
detail), an unsupported tool, LangChain tool-call parsing, and that no arbitrary
tool can be executed. No paid API requests are made — LLM tools use injected fake
producers.
