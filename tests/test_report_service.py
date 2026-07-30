"""Tests for the final-report service. All model results are mocked."""

import json

import pytest

from src.interview_service import ModelResponseError, ServiceInputError
from src.models import (
    AnswerEvaluation,
    FinalInterviewReport,
    InterviewConfiguration,
    InterviewQuestion,
    ModelSettings,
)
from src.openrouter_client import ChatResult
from src.pricing_service import PricingService
from src.report_service import ReportService

MODEL = "openai/gpt-5-mini"


class FakeClient:
    def __init__(self, contents):
        self._contents = list(contents)
        self.calls: list[dict] = []

    def create_chat_completion(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        content = self._contents.pop(0)
        return ChatResult(
            content=content,
            model=kwargs["model"],
            prompt_tokens=200,
            completion_tokens=120,
            total_tokens=320,
            reported_cost=0.004,
            duration_seconds=1.1,
            request_id="gen-report",
        )


def _pricing() -> PricingService:
    return PricingService(
        models_fetcher=lambda: [
            {
                "id": MODEL,
                "pricing": {"prompt": "0.0000006", "completion": "0.0000018"},
                "supported_parameters": ["temperature", "max_tokens", "response_format"],
            }
        ]
    )


def _config() -> InterviewConfiguration:
    return InterviewConfiguration(
        target_role="Registered Nurse",
        industry_or_sector="healthcare",
        career_level="senior",
        interview_types=["behavioural"],
        interviewer_persona="neutral",
        difficulty="moderate",
        response_detail="standard",
    )


def _settings() -> ModelSettings:
    return ModelSettings(model=MODEL, prompt_technique="rubric_json")


def _question(qid: int) -> InterviewQuestion:
    return InterviewQuestion(
        question_id=qid,
        question=f"Question number {qid}?",
        question_type="behavioural",
        competency="teamwork",
        difficulty="moderate",
        interviewer_intent="Assess collaboration.",
        expected_answer_elements=["situation", "action", "result"],
    )


def _evaluation(score: int) -> AnswerEvaluation:
    return AnswerEvaluation(
        overall_score=score,
        relevance=7,
        structure=7,
        evidence=6,
        role_knowledge=7,
        problem_solving=7,
        communication=7,
        credibility=7,
        strengths=["clear communication"],
        improvement_areas=["add measurable outcomes"],
        missing_evidence=["metrics"],
        stronger_answer_structure="STAR",
        improved_example_answer="Example.",
        follow_up_question="What changed?",
    )


def _report_json() -> str:
    section = ["item"]
    return json.dumps(
        {
            "overall_readiness_score": 68,
            "performance_summary": "Solid, with clear gaps to close.",
            "strongest_competencies": section,
            "development_priorities": section,
            "recurring_answer_patterns": section,
            "highest_risk_questions": section,
            "evidence_gaps": section,
            "recommended_practice_actions": section,
            "final_interview_checklist": section,
        }
    )


class TestGenerateReport:
    def test_returns_report_and_usage(self) -> None:
        service = ReportService(FakeClient([_report_json()]), _pricing())
        report, usage = service.generate_report(
            _config(),
            [_question(1), _question(2)],
            ["answer one", "answer two"],
            [_evaluation(70), _evaluation(60)],
            _settings(),
        )
        assert isinstance(report, FinalInterviewReport)
        assert usage.total_tokens == 320
        assert usage.cost_source == "reported"

    def test_report_is_grounded_in_completed_evidence(self) -> None:
        client = FakeClient([_report_json()])
        service = ReportService(client, _pricing())
        service.generate_report(
            _config(),
            [_question(1)],
            ["my recorded answer"],
            [_evaluation(70)],
            _settings(),
        )
        system = client.calls[0]["messages"][0]["content"]
        user = client.calls[0]["messages"][1]["content"]
        # Prompt instructs grounding and separation of patterns from assumptions.
        assert "completed" in system.lower()
        assert "separate observed answer patterns from assumptions" in system.lower()
        # Guardrails forbid protected characteristics.
        assert "protected characteristics" in system.lower()
        # The actual answer text is present as evidence.
        assert "my recorded answer" in user

    def test_empty_history_is_rejected(self) -> None:
        service = ReportService(FakeClient([_report_json()]), _pricing())
        with pytest.raises(ServiceInputError):
            service.generate_report(_config(), [], [], [], _settings())

    def test_mismatched_lengths_rejected(self) -> None:
        service = ReportService(FakeClient([_report_json()]), _pricing())
        with pytest.raises(ServiceInputError):
            service.generate_report(
                _config(),
                [_question(1), _question(2)],
                ["only one answer"],
                [_evaluation(70)],
                _settings(),
            )

    def test_two_failures_raise_model_response_error(self) -> None:
        service = ReportService(FakeClient(["bad", "still bad"]), _pricing())
        with pytest.raises(ModelResponseError):
            service.generate_report(
                _config(),
                [_question(1)],
                ["answer"],
                [_evaluation(70)],
                _settings(),
            )
