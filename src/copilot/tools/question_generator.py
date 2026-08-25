"""Interview Question Generator — LLM structured output.

Generates likely interview questions across relevant categories, grounded in the
supplied role, requirements, career-intelligence findings and retrieved evidence.
This prepares questions from the Career Intelligence context; it does NOT run an
interview simulation — that remains the Interview Practice module's job.
"""

from __future__ import annotations

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.tools.schemas import InterviewQuestionSet, QuestionGeneratorArgs
from src.copilot.tools.structured import StructuredProducer, build_structured_producer

__all__ = ["generate_questions", "SYSTEM_PROMPT"]

SYSTEM_PROMPT = """You generate likely interview questions to help a candidate \
prepare. Rules:
- Ground questions in the supplied role, requirements, findings and evidence. Do \
not fabricate facts about the employer or candidate.
- Produce questions grouped by category. Use the requested focus categories if \
given; otherwise choose the most relevant from: {categories}.
- Generate about {per_category} questions per category.
- Questions only — do not answer them, and do not include chain-of-thought."""


def _messages(args: QuestionGeneratorArgs) -> list[dict]:
    categories = args.focus or list(constants.QUESTION_CATEGORIES)
    system = SYSTEM_PROMPT.format(
        categories=", ".join(constants.QUESTION_CATEGORIES),
        per_category=args.per_category,
    )
    parts = [f"ROLE: {args.role}", f"FOCUS CATEGORIES: {', '.join(categories)}"]
    if args.requirements:
        parts.append("REQUIREMENTS:\n- " + "\n- ".join(args.requirements))
    if args.findings:
        parts.append("CAREER-INTELLIGENCE FINDINGS:\n- " + "\n- ".join(args.findings))
    if args.evidence:
        parts.append("RETRIEVED EVIDENCE:\n- " + "\n- ".join(args.evidence))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]


def generate_questions(
    args: QuestionGeneratorArgs,
    *,
    producer: StructuredProducer | None = None,
    config: CopilotConfig | None = None,
) -> InterviewQuestionSet:
    """Generate a structured :class:`InterviewQuestionSet` for the role."""
    producer = producer or build_structured_producer(config, InterviewQuestionSet)
    result = producer(_messages(args))
    if not isinstance(result, InterviewQuestionSet):
        result = InterviewQuestionSet.model_validate(result)
    if not result.role:
        result.role = args.role
    return result
