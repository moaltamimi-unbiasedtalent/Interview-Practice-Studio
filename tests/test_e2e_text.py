"""End-to-end interview pipeline test (Text Practice), fully mocked.

Drives the real services through a complete interview — strategy → question →
answer → evaluation → Deep Dive → final report — with a fake OpenRouter client.
No network/paid calls. Voice and Live reuse the same evaluation pipeline (a
transcript is just an answer string), so this covers the shared engine for all
three modes.
"""

import json

from src.evaluation_service import EvaluationService
from src.interview_service import InterviewService
from src.models import (
    AnswerEvaluation,
    BranchQuestion,
    FinalInterviewReport,
    InterviewConfiguration,
    InterviewQuestion,
    InterviewStrategy,
    ModelSettings,
)
from src.openrouter_client import ChatResult
from src.pricing_service import PricingService
from src.report_service import ReportService

MODEL = "openai/gpt-5-mini"


class SequencedClient:
    """Returns queued JSON bodies in order; records every call."""

    def __init__(self, bodies):
        self._bodies = list(bodies)
        self.calls = 0

    def create_chat_completion(self, **kwargs) -> ChatResult:
        self.calls += 1
        content = self._bodies.pop(0)
        return ChatResult(
            content=content,
            model=kwargs["model"],
            prompt_tokens=120,
            completion_tokens=80,
            total_tokens=200,
            reported_cost=0.0012,
            duration_seconds=0.4,
            request_id=f"gen-{self.calls}",
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


def _strategy_json() -> str:
    section = ["item"]
    return json.dumps(
        {
            "role_summary": "A profession-neutral summary.",
            "likely_interview_stages": section,
            "critical_competencies": section,
            "likely_question_themes": section,
            "probable_challenges": section,
            "evidence_to_prepare": section,
            "technical_or_functional_topics": section,
            "behavioural_topics": section,
            "questions_for_interviewer": section,
            "preparation_priorities": section,
        }
    )


def _question_json(qid: int) -> str:
    return json.dumps(
        {
            "question_id": qid,
            "question": f"Question {qid}: describe a challenge.",
            "question_type": "behavioural",
            "competency": "resilience",
            "difficulty": "moderate",
            "interviewer_intent": "See how they handle pressure.",
            "expected_answer_elements": ["situation", "action", "result"],
        }
    )


def _evaluation_json(score: int = 72) -> str:
    return json.dumps(
        {
            "overall_score": score,
            "relevance": 7,
            "structure": 7,
            "evidence": 6,
            "role_knowledge": 7,
            "problem_solving": 7,
            "communication": 7,
            "credibility": 7,
            "strengths": ["clear"],
            "improvement_areas": ["add metrics"],
            "missing_evidence": ["numbers"],
            "stronger_answer_structure": "STAR",
            "improved_example_answer": "Example.",
            "follow_up_question": "What changed?",
        }
    )


def _branch_json() -> str:
    return json.dumps(
        {
            "branch_id": "model-provided-ignored",
            "parent_question_id": 999,
            "question": "Deep dive: why that approach?",
            "branch_mode": "deepen_reasoning",
            "focus_area": "reasoning",
            "interviewer_intent": "Probe the reasoning.",
            "expected_answer_elements": ["rationale"],
            "difficulty": "moderate",
            "depth": 1,
        }
    )


def _report_json() -> str:
    section = ["item"]
    return json.dumps(
        {
            "overall_readiness_score": 68,
            "performance_summary": "Solid, with clear gaps.",
            "strongest_competencies": section,
            "development_priorities": section,
            "recurring_answer_patterns": section,
            "highest_risk_questions": section,
            "evidence_gaps": section,
            "recommended_practice_actions": section,
            "final_interview_checklist": section,
        }
    )


def test_full_text_interview_pipeline() -> None:
    pricing = _pricing()
    client = SequencedClient(
        [
            _strategy_json(),  # strategy
            _question_json(1),  # first question
            _evaluation_json(74),  # answer 1 evaluation
            _branch_json(),  # Deep Dive question
            _evaluation_json(70),  # Deep Dive answer evaluation
            _question_json(2),  # next main question
            _evaluation_json(66),  # answer 2 evaluation
            _report_json(),  # final report
        ]
    )
    interview = InterviewService(client, pricing)
    evaluation = EvaluationService(client, pricing)
    report_service = ReportService(client, pricing)
    config, settings = _config(), _settings()

    # 1. Strategy
    strategy, _ = interview.generate_strategy(config, settings)
    assert isinstance(strategy, InterviewStrategy)

    # 2. First question
    q1, _ = interview.generate_next_question(config, settings, current_question_number=1)
    assert isinstance(q1, InterviewQuestion)

    # 3. Answer + evaluation
    eval1, _ = evaluation.evaluate_answer(config, q1.question, "My answer to Q1.", settings)
    assert isinstance(eval1, AnswerEvaluation)

    # 4. Deep Dive (bounded by depth) — authoritative linkage applied by service
    branch, _ = interview.generate_branch_question(
        config,
        settings,
        parent_question=q1,
        candidate_answer="My answer to Q1.",
        evaluation=eval1,
        branch_mode="deepen_reasoning",
        depth=1,
        branch_id="branch-1",
    )
    assert isinstance(branch, BranchQuestion)
    assert branch.parent_question_id == q1.question_id  # not the model's 999
    assert branch.depth == 1

    branch_eval, _ = evaluation.evaluate_answer(
        config, branch.question, "Deep dive answer.", settings
    )
    assert isinstance(branch_eval, AnswerEvaluation)

    # 5. Second main question + evaluation
    q2, _ = interview.generate_next_question(config, settings, current_question_number=2)
    eval2, _ = evaluation.evaluate_answer(config, q2.question, "My answer to Q2.", settings)
    assert q2.question_id == 2

    # 6. Final report grounded in the completed interview
    report, usage = report_service.generate_report(
        config,
        [q1, q2],
        ["My answer to Q1.", "My answer to Q2."],
        [eval1, eval2],
        settings,
    )
    assert isinstance(report, FinalInterviewReport)
    assert 0 <= report.overall_readiness_score <= 100

    # Every model call was consumed and usage was recorded for cost accounting.
    assert client.calls == 8
    assert pricing.session_totals().requests >= 8
