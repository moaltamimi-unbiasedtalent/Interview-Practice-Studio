"""Final-report service (use case 4).

Produces a :class:`FinalInterviewReport` from the completed interview evidence
(questions, answers and evaluations) plus a :class:`UsageRecord`. It reuses the
shared generation base from :mod:`src.interview_service`.

The report is grounded only in what happened during the session: the prompt
instructs the model to base conclusions on the completed evidence, to separate
observed answer patterns from assumptions, and never to infer protected
characteristics or diagnose personality or health.
"""

from __future__ import annotations

from collections.abc import Sequence

from src import prompts
from src.interview_service import BaseGenerationService, ServiceInputError
from src.models import (
    AnswerEvaluation,
    FinalInterviewReport,
    InterviewConfiguration,
    InterviewQuestion,
    ModelSettings,
    UsageRecord,
)

__all__ = ["ReportService"]


class ReportService(BaseGenerationService):
    """Generates the end-of-session interview report."""

    def generate_report(
        self,
        config: InterviewConfiguration,
        questions: Sequence[InterviewQuestion],
        answers: Sequence[str],
        evaluations: Sequence[AnswerEvaluation],
        settings: ModelSettings,
    ) -> tuple[FinalInterviewReport, UsageRecord]:
        """Use case 4 — produce the final interview-readiness report."""
        if not questions or not answers:
            raise ServiceInputError(
                "A final report needs at least one completed question and answer."
            )
        if not (len(questions) == len(answers) == len(evaluations)):
            raise ServiceInputError(
                "Questions, answers and evaluations must be the same length."
            )

        self._screen_context(config.job_description, config.company_context)

        previous_questions = [q.question for q in questions]
        previous_answers = list(answers)
        previous_summaries = [
            f"Q{i}: score {e.overall_score}/100; strengths: "
            + "; ".join(e.strengths[:2])
            + "; improve: "
            + "; ".join(e.improvement_areas[:2])
            for i, e in enumerate(evaluations, start=1)
        ]

        return self._generate(
            task=prompts.TASK_REPORT,
            schema=FinalInterviewReport,
            config=config,
            settings=settings,
            user_message_kwargs={
                "previous_questions": previous_questions,
                "previous_answers": previous_answers,
                "previous_evaluation_summaries": previous_summaries,
            },
        )
