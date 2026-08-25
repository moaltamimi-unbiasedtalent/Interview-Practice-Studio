"""Job Description Analyzer — LLM structured output.

Extracts structured role requirements from a pasted job description. It must not
invent requirements: anything not explicitly stated goes into
``interpretation_notes`` (reasonable interpretation), kept separate from the
explicit requirement lists.
"""

from __future__ import annotations

from src.copilot.config import CopilotConfig
from src.copilot.tools.schemas import JobAnalyzerArgs, RoleRequirements
from src.copilot.tools.structured import StructuredProducer, build_structured_producer

__all__ = ["analyze_job", "SYSTEM_PROMPT"]

SYSTEM_PROMPT = """You extract structured requirements from a job description for \
interview preparation. Rules:
- Use ONLY the supplied job description. Do NOT invent requirements, tools or \
expectations that are not present in the text.
- Put requirements explicitly stated in the JD into the named lists \
(required_skills, preferred_skills, technologies, key_responsibilities, \
leadership_expectations, stakeholder_expectations).
- Put anything that is a reasonable interpretation but NOT explicitly stated into \
interpretation_notes, clearly separate from the explicit lists.
- role_title and seniority: fill only where evident; otherwise leave null.
- likely_interview_themes: themes a candidate should expect, grounded in the JD.
- Be concise; do not include chain-of-thought."""


def _messages(args: JobAnalyzerArgs) -> list[dict]:
    focus = f"\nEmphasise the '{args.focus}' aspect where relevant." if args.focus else ""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + focus},
        {"role": "user", "content": f"JOB DESCRIPTION:\n{args.job_description}"},
    ]


def analyze_job(
    args: JobAnalyzerArgs,
    *,
    producer: StructuredProducer | None = None,
    config: CopilotConfig | None = None,
) -> RoleRequirements:
    """Analyse a job description into :class:`RoleRequirements`."""
    producer = producer or build_structured_producer(config, RoleRequirements)
    result = producer(_messages(args))
    if not isinstance(result, RoleRequirements):
        result = RoleRequirements.model_validate(result)
    return result
