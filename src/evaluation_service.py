"""Answer-evaluation service (use case 3).

Evaluates the answer the candidate actually submitted and returns a structured
:class:`AnswerEvaluation` plus a :class:`UsageRecord`. It reuses the shared
generation base from :mod:`src.interview_service`, so it inherits the same
registry / prompt / security / client / parser wiring, dependency injection and
controlled domain errors.
"""

from __future__ import annotations

from src import prompts
from src.interview_service import BaseGenerationService
from src.models import AnswerEvaluation, InterviewConfiguration, ModelSettings, UsageRecord

__all__ = ["EvaluationService"]


class EvaluationService(BaseGenerationService):
    """Evaluates a single candidate answer to the current question."""

    def evaluate_answer(
        self,
        config: InterviewConfiguration,
        question: str,
        candidate_answer: str,
        settings: ModelSettings,
    ) -> tuple[AnswerEvaluation, UsageRecord]:
        """Use case 3 — evaluate the submitted answer.

        The candidate's answer is never blocked by injection screening (it must
        always be evaluated); it is protected by being framed as untrusted data
        in the prompt. Context fields are still screened.
        """
        self._screen_context(config.job_description, config.company_context)

        return self._generate(
            task=prompts.TASK_EVALUATION,
            schema=AnswerEvaluation,
            config=config,
            settings=settings,
            user_message_kwargs={
                "question": question,
                "candidate_answer": candidate_answer,
            },
        )
