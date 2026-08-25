"""Domain tool calling for Career Intelligence Copilot.

Four domain-relevant tools, exposed through LangChain tool calling over the
existing OpenRouter integration — never as an unrestricted autonomous agent:

1. Job Description Analyzer      (LLM, structured output)
2. Candidate Gap Analyzer        (deterministic Python)
3. Preparation Plan Calculator   (deterministic Python arithmetic)
4. Interview Question Generator  (LLM, structured output)

The model may only invoke these registered tools; it can never call arbitrary
Python, shell, filesystem or network functions. Every call is captured as a safe
:class:`~src.copilot.models.ToolExecution` record (no raw candidate/JD text).
"""

from src.copilot.tools.registry import (
    ToolInvoker,
    ToolResult,
    build_langchain_tools,
    build_tool_registry,
    parse_tool_calls,
)

__all__ = [
    "ToolInvoker",
    "ToolResult",
    "build_tool_registry",
    "build_langchain_tools",
    "parse_tool_calls",
]
