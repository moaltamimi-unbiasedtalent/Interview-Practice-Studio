"""Interview orchestration services.

This module hosts the shared generation base class (used by all services) and
the two interview use cases: generating a preparation strategy and generating
the next interview question.

Every service here is:

* **framework-independent** — no Streamlit, no globals; all state is injected.
* **dependency-injected** — the OpenRouter client and pricing service are
  passed in, so tests can supply fakes with canned model results.
* **safe** — it uses the prompt registry (technique selection), the prompt
  library (role-separated messages), the security layer (injection screening
  and output inspection) and the response parser (validated output with one
  repair round), and it converts every failure into a controlled domain error.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field

from src import constants, prompts, security
from src import prompt_registry as registry
from src.models import (
    AnswerEvaluation,
    BranchQuestion,
    InterviewConfiguration,
    InterviewQuestion,
    InterviewStrategy,
    ModelSettings,
    UsageRecord,
)
from src.openrouter_client import ChatResult, OpenRouterClient, OpenRouterError
from src.pricing_service import PricingService
from src.response_parser import ResponseParseError, parse_structured_output
from src.structured_output import build_structured_response_format

__all__ = [
    "ServiceError",
    "ServiceInputError",
    "ModelResponseError",
    "BaseGenerationService",
    "InterviewService",
]

_LOGGER = logging.getLogger(__name__)


# --- Domain errors -----------------------------------------------------------


class ServiceError(Exception):
    """Base class for controlled service errors (safe to show to a user)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class ServiceInputError(ServiceError):
    """The request could not be accepted (bad technique, blocked input)."""


class ModelResponseError(ServiceError):
    """The model call failed, was unsafe, or could not be parsed."""


class _TruncatedOutput(Exception):
    """Internal signal: a response was cut off at the output-token limit.

    Raised inside the generation helpers and translated by :meth:`_generate`
    into a controlled, actionable :class:`ModelResponseError`. A same-budget
    retry cannot help, so it is never retried.
    """


# --- Shared generation base --------------------------------------------------


class BaseGenerationService:
    """Shared orchestration for a single structured model request.

    Subclasses call :meth:`_generate` with a task, schema and message context.
    The base wires together the registry, prompt library, security layer,
    OpenRouter client, response parser and pricing service, and returns the
    validated object together with a :class:`UsageRecord`.
    """

    def __init__(
        self, client: OpenRouterClient, pricing_service: PricingService
    ) -> None:
        # Injected dependencies — no module-level or global state.
        self._client = client
        self._pricing = pricing_service

    # -- input screening ------------------------------------------------------

    @staticmethod
    def _screen_context(*texts: str) -> None:
        """Block context text that clearly attempts prompt injection.

        Applied to context fields (job description, company context, background)
        — not to a candidate's own answer, which must always be evaluated.
        """
        for text in texts:
            if not text:
                continue
            assessment = security.detect_injection(text)
            if assessment.decision == security.BLOCK:
                raise ServiceInputError(
                    "The provided context appears to contain a prompt-injection "
                    "attempt and was blocked. Please remove instructions aimed "
                    "at the assistant and try again."
                )

    # -- core request ---------------------------------------------------------

    def _generate(
        self,
        *,
        task: str,
        schema: type,
        config: InterviewConfiguration,
        settings: ModelSettings,
        user_message_kwargs: dict,
        overrides: dict | None = None,
    ):
        """Run one structured request; return ``(validated_object, usage)``.

        ``overrides`` are caller-authoritative fields applied before validation
        (see :func:`src.response_parser.parse_structured_output`).
        """
        technique_id = settings.prompt_technique
        # Use the prompt registry to validate the technique and fail safely.
        try:
            registry.get_technique(technique_id)
        except registry.UnknownPromptTechniqueError as exc:
            raise ServiceInputError(str(exc)) from exc

        messages = prompts.build_task_messages(
            task, technique_id, config, **user_message_kwargs
        )

        supported = self._pricing.supported_parameters(settings.model)
        caps = self._pricing.capabilities(settings.model)
        billed: list[ChatResult] = []  # every actual call, for honest cost

        try:
            if caps.supports_strict_schema:
                # Provider enforces the schema, so the shape is guaranteed and
                # no model-based repair is needed. One controlled fallback to
                # the defensive path is kept for the rare enforcement failure.
                try:
                    obj = self._run_strict(
                        schema, messages, settings, supported, overrides, billed
                    )
                except ResponseParseError as strict_error:
                    self._log_attempt_failure(
                        task, schema, settings.model, "strict",
                        strict=True, reason=strict_error.message,
                        results=list(billed),
                    )
                    obj = self._run_defensive(
                        schema, messages, settings, supported, overrides, billed
                    )
            else:
                # No schema enforcement: keep the defensive parser and exactly
                # one bounded repair attempt.
                obj = self._run_defensive(
                    schema, messages, settings, supported, overrides, billed
                )
        except _TruncatedOutput as exc:
            self._log_attempt_failure(
                task, schema, settings.model, "truncated",
                strict=caps.supports_strict_schema, reason="finish_reason=length",
                results=list(billed),
            )
            self._record_billed(settings.model, billed)
            raise ModelResponseError(
                "The response was cut off because it reached the output-token "
                "limit. Increase 'Maximum output tokens' in the developer "
                "settings and try again."
            ) from exc
        except ResponseParseError as exc:
            self._log_attempt_failure(
                task, schema, settings.model, "final",
                strict=caps.supports_strict_schema, reason=exc.message,
                results=list(billed),
            )
            self._record_billed(settings.model, billed)
            raise ModelResponseError(exc.message) from exc

        usage = self._build_usage(settings.model, billed)
        self._pricing.record_usage(usage)
        return obj, usage

    def _run_strict(
        self, schema, messages, settings, supported, overrides, billed
    ):
        """Single strict-JSON-Schema request; no model-based repair.

        The provider is asked (via ``require_parameters`` routing) to enforce a
        strict schema generated from the Pydantic model, so the returned text is
        already the right shape. It is still validated by the model afterwards.
        """
        response_format = build_structured_response_format(schema, schema.__name__)
        result = self._call_model(
            messages, settings, response_format, supported, require_parameters=True
        )
        billed.append(result)
        self._guard_output(result.content)
        try:
            return parse_structured_output(result.content, schema, overrides=overrides)
        except ResponseParseError:
            if result.finish_reason == "length":
                raise _TruncatedOutput() from None
            raise

    def _run_defensive(
        self, schema, messages, settings, supported, overrides, billed
    ):
        """Defensive parse with exactly one bounded model-based repair round.

        Used for models without schema enforcement (and as the single fallback
        from the strict path). A json_object hint is sent when the model
        supports it; otherwise the prompt's output contract carries the shape.
        """
        response_format = (
            {"type": "json_object"} if "response_format" in supported else None
        )
        attempt_results: list[ChatResult] = []

        primary = self._call_model(messages, settings, response_format, supported)
        attempt_results.append(primary)
        billed.append(primary)
        self._guard_output(primary.content)

        def repair(bad_text: str, error: str) -> str:
            repair_messages = self._repair_messages(bad_text, error, schema)
            repaired = self._call_model(
                repair_messages, settings, response_format, supported
            )
            attempt_results.append(repaired)
            billed.append(repaired)
            # The repaired text is model output too: same safety scan as primary.
            self._guard_output(repaired.content)
            return repaired.content

        try:
            return parse_structured_output(
                primary.content, schema, repair=repair, overrides=overrides
            )
        except ResponseParseError:
            if any(r.finish_reason == "length" for r in attempt_results):
                raise _TruncatedOutput() from None
            raise

    def _log_attempt_failure(
        self, task, schema, model, attempt, *, strict, reason, results
    ) -> None:
        """Log SAFE metadata only about a failed generation.

        Never logs request or response content (candidate answers, backgrounds,
        job descriptions, transcripts or model-generated bodies) or API keys —
        only the metadata needed to diagnose a failure.
        """
        last = results[-1] if results else None
        _LOGGER.warning(
            "generation failed: task=%s schema=%s model=%s attempt=%s strict=%s "
            "request_id=%s finish_reason=%s duration=%.3fs prompt_tokens=%s "
            "completion_tokens=%s reason=%s",
            task,
            schema.__name__,
            model,
            attempt,
            strict,
            getattr(last, "request_id", None),
            getattr(last, "finish_reason", None),
            getattr(last, "duration_seconds", 0.0) or 0.0,
            getattr(last, "prompt_tokens", None),
            getattr(last, "completion_tokens", None),
            reason,
        )

    def _record_billed(self, model: str, billed: list[ChatResult]) -> None:
        """Record usage for calls that were made but did not yield a result.

        Failed attempts still consume tokens the provider bills for, so their
        usage is recorded (for honest session totals) even though no validated
        object is returned.
        """
        if billed:
            self._pricing.record_usage(self._build_usage(model, billed))

    def _effective_max_tokens(self, settings: ModelSettings) -> int:
        """Never request more output than the model itself allows.

        The requested budget is capped at the model's advertised
        ``max_completion_tokens`` when metadata provides it; otherwise the
        user's setting is used unchanged. This only ever lowers the request, so
        it cannot cause an over-budget call to a model with a small limit.

        The pricing dependency is injected, and across a Streamlit hot reload a
        previously-cached instance can predate this accessor. Resolve it with
        ``getattr`` so a missing accessor degrades to the configured budget
        rather than raising ``AttributeError`` into the UI.
        """
        getter = getattr(self._pricing, "max_completion_tokens", None)
        if not callable(getter):
            return settings.max_tokens
        cap = getter(settings.model)
        if isinstance(cap, int) and not isinstance(cap, bool) and cap > 0:
            return min(settings.max_tokens, cap)
        return settings.max_tokens

    def _call_model(
        self,
        messages,
        settings: ModelSettings,
        response_format,
        supported,
        *,
        require_parameters: bool = False,
    ) -> ChatResult:
        try:
            return self._client.create_chat_completion(
                model=settings.model,
                messages=messages,
                # Capability-gated by the client: temperature is omitted for
                # models that do not support it, so passing it here is safe.
                temperature=settings.temperature,
                max_tokens=self._effective_max_tokens(settings),
                response_format=response_format,
                supported_parameters=supported,
                # Reasoning models (e.g. GPT-5) otherwise spend the whole output
                # budget on internal reasoning and return no text
                # (finish_reason=length). Request the smallest reasoning
                # allocation so the token budget goes to the structured answer.
                # The client only forwards this to models that advertise
                # "reasoning" in their metadata; it is dropped for the rest.
                reasoning={"effort": constants.DEFAULT_REASONING_EFFORT},
                require_parameters=require_parameters,
            )
        except OpenRouterError as exc:
            # Log SAFE metadata only (status + category, never content/keys).
            _LOGGER.warning(
                "openrouter call failed: model=%s status=%s category=%s",
                settings.model,
                exc.status_code,
                exc.category,
            )
            # Convert transport/API errors into a controlled domain error.
            raise ModelResponseError(exc.message) from exc

    def _guard_output(self, content: str) -> None:
        assessment = security.inspect_output(content, expect_json=False)
        if assessment.decision == security.BLOCK:
            raise ModelResponseError(
                "The model response failed a safety check and was not used."
            )

    @staticmethod
    def _repair_messages(bad_text: str, error: str, schema: type) -> list[dict]:
        """Build a minimal, self-contained JSON-repair request."""
        keys = ", ".join(schema.model_fields)
        system = (
            "You fix malformed JSON. Return ONLY a single valid JSON object with "
            "exactly these keys and nothing else — no markdown, no commentary: "
            f"{keys}. Do not invent values; preserve the original content and "
            "only correct the JSON structure."
        )
        user = (
            f"The following was supposed to be a valid {schema.__name__} JSON "
            f"object but failed with: {error}\n\n{bad_text}"
        )
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

    def _build_usage(self, model: str, results: Sequence[ChatResult]) -> UsageRecord:
        """Aggregate usage across the primary call and any repair call."""
        prompt_tokens = sum(r.prompt_tokens for r in results)
        completion_tokens = sum(r.completion_tokens for r in results)
        reported = [r.reported_cost for r in results if r.reported_cost is not None]
        reported_cost = sum(reported) if reported else None
        duration = sum(r.duration_seconds for r in results)
        return self._pricing.build_usage_record(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            reported_cost=reported_cost,
            request_duration_seconds=duration,
        )


# --- Interview service -------------------------------------------------------


@dataclass(frozen=True)
class QuestionHistory:
    """Prior turns supplied when generating the next question."""

    questions: Sequence[InterviewQuestion] = field(default_factory=tuple)
    answers: Sequence[str] = field(default_factory=tuple)
    evaluations: Sequence[AnswerEvaluation] = field(default_factory=tuple)


class InterviewService(BaseGenerationService):
    """Generates interview strategies and the next interview question."""

    def generate_strategy(
        self, config: InterviewConfiguration, settings: ModelSettings
    ) -> tuple[InterviewStrategy, UsageRecord]:
        """Use case 1 — produce a preparation strategy for the role."""
        self._screen_context(
            config.job_description,
            config.company_context,
            config.candidate_background,
        )
        return self._generate(
            task=prompts.TASK_STRATEGY,
            schema=InterviewStrategy,
            config=config,
            settings=settings,
            user_message_kwargs={},
        )

    def generate_next_question(
        self,
        config: InterviewConfiguration,
        settings: ModelSettings,
        *,
        current_question_number: int,
        history: QuestionHistory | None = None,
    ) -> tuple[InterviewQuestion, UsageRecord]:
        """Use case 2 — generate the next, non-repeated interview question."""
        history = history or QuestionHistory()
        self._screen_context(
            config.job_description,
            config.company_context,
            config.candidate_background,
        )

        # Keep every previous question (short; needed so the model does not
        # repeat one) and every compact evaluation summary (drives difficulty
        # adaptation). Bound only the full answer texts — the dominant token
        # cost — to the most recent few, so the prompt cannot grow without limit
        # across a long interview and overflow the model's context window.
        previous_questions = [q.question for q in history.questions]
        previous_answers = list(history.answers)[-constants.MAX_HISTORY_ANSWERS :]
        previous_summaries = [
            f"score {e.overall_score}/100; improve: "
            + "; ".join(e.improvement_areas[:2])
            for e in history.evaluations
        ]

        return self._generate(
            task=prompts.TASK_QUESTION,
            schema=InterviewQuestion,
            config=config,
            settings=settings,
            user_message_kwargs={
                "previous_questions": previous_questions,
                "previous_answers": previous_answers,
                "previous_evaluation_summaries": previous_summaries,
                "current_question_number": current_question_number,
            },
        )

    def generate_branch_question(
        self,
        config: InterviewConfiguration,
        settings: ModelSettings,
        *,
        parent_question: InterviewQuestion,
        candidate_answer: str,
        evaluation: AnswerEvaluation,
        branch_mode: str,
        depth: int,
        branch_id: str,
        previous_branch_questions: "Sequence[str] | None" = None,
        previous_branch_answers: "Sequence[str] | None" = None,
    ) -> tuple[BranchQuestion, UsageRecord]:
        """Deep Dive — generate one deeper question that branches from an answer.

        Reuses the shared generation pipeline (registry, prompts, security,
        client, parser, pricing). The linkage fields (branch_id,
        parent_question_id, branch_mode, depth) are set authoritatively here
        rather than trusted from the model, so a branch is always correctly
        anchored to its parent question and depth.
        """
        self._screen_context(config.job_description, config.company_context)

        summary = (
            f"parent score {evaluation.overall_score}/100; improve: "
            + "; ".join(evaluation.improvement_areas[:2])
        )
        return self._generate(
            task=prompts.TASK_BRANCH,
            schema=BranchQuestion,
            config=config,
            settings=settings,
            user_message_kwargs={
                "question": parent_question.question,
                "candidate_answer": candidate_answer,
                "previous_evaluation_summaries": [summary],
                "previous_questions": list(previous_branch_questions or []),
                "previous_answers": list(previous_branch_answers or []),
                "branch_mode": branch_mode,
                "branch_depth": depth,
            },
            # Authoritative linkage — applied before validation, never trusted
            # from the model.
            overrides={
                "branch_id": branch_id,
                "parent_question_id": parent_question.question_id,
                "branch_mode": branch_mode,
                "depth": depth,
            },
        )
