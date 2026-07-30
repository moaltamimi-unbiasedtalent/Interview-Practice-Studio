"""Generic-profession regression tests (Phase 11).

Proves the app makes no inappropriate assumptions about a candidate's
profession: the same neutral system prompt is used for every role, the role
lives only in the user message (as data), and the domain models accept every
representative role. Deterministic prompt construction only — no API calls.
"""

import pytest

from src import prompts
from src.models import InterviewConfiguration, ModelSettings
from src.evaluation_service import EvaluationService
from src.openrouter_client import ChatResult
from src.pricing_service import PricingService

# Ten representative professions with plausible, valid session parameters.
PROFESSIONS = [
    ("Junior Software Developer", "technology", "junior", ["technical"]),
    ("Senior Accountant", "finance", "senior", ["technical", "behavioural"]),
    ("Registered Nurse", "healthcare", "mid", ["situational", "behavioural"]),
    ("Electrician", "skilled trades", "mid", ["technical", "situational"]),
    ("Operations Manager", "logistics", "manager", ["leadership", "behavioural"]),
    ("Marketing Director", "media", "director", ["leadership", "culture_values"]),
    ("Teacher", "education", "mid", ["behavioural", "situational"]),
    ("Compliance Manager", "legal", "manager", ["competency", "stakeholder"]),
    ("Sales Manager", "retail", "manager", ["behavioural", "stakeholder"]),
    ("Chief Executive Officer", "general business", "executive", ["executive_board"]),
]

PARAM_IDS = [role for role, *_ in PROFESSIONS]


def _config(role: str, sector: str, level: str, types: list[str]) -> InterviewConfiguration:
    return InterviewConfiguration(
        target_role=role,
        industry_or_sector=sector,
        career_level=level,
        interview_types=types,
        interviewer_persona="neutral",
        difficulty="moderate",
        response_detail="standard",
        job_description=f"Responsibilities relevant to a {role}.",
    )


class FakeClient:
    """Returns a canned evaluation regardless of role (no network)."""

    def __init__(self) -> None:
        self.roles_seen: list[str] = []

    def create_chat_completion(self, **kwargs) -> ChatResult:
        self.roles_seen.append(kwargs["messages"][1]["content"])
        import json

        content = json.dumps(
            {
                "overall_score": 70,
                "relevance": 7,
                "structure": 7,
                "evidence": 6,
                "role_knowledge": 7,
                "problem_solving": 7,
                "communication": 7,
                "credibility": 7,
                "strengths": ["clear"],
                "improvement_areas": ["add detail"],
                "missing_evidence": ["metrics"],
                "stronger_answer_structure": "STAR",
                "improved_example_answer": "Example.",
                "follow_up_question": "What changed?",
            }
        )
        return ChatResult(
            content=content,
            model=kwargs["model"],
            prompt_tokens=50,
            completion_tokens=25,
            total_tokens=75,
            reported_cost=0.0001,
            duration_seconds=0.2,
            request_id="gen-x",
        )


def _pricing() -> PricingService:
    return PricingService(
        models_fetcher=lambda: [
            {
                "id": "openai/gpt-5-mini",
                "pricing": {"prompt": "0.0000006", "completion": "0.0000018"},
                "supported_parameters": ["temperature", "max_tokens", "response_format"],
            }
        ]
    )


class TestGenericProfessionSupport:
    @pytest.mark.parametrize(
        "role,sector,level,types", PROFESSIONS, ids=PARAM_IDS
    )
    def test_configuration_accepts_every_profession(
        self, role, sector, level, types
    ) -> None:
        config = _config(role, sector, level, types)
        assert config.target_role == role
        assert config.career_level == level

    @pytest.mark.parametrize(
        "role,sector,level,types", PROFESSIONS, ids=PARAM_IDS
    )
    def test_system_prompt_is_neutral_role_only_in_user_message(
        self, role, sector, level, types
    ) -> None:
        config = _config(role, sector, level, types)
        for task in (
            prompts.TASK_STRATEGY,
            prompts.TASK_QUESTION,
            prompts.TASK_EVALUATION,
        ):
            kwargs = {}
            if task == prompts.TASK_EVALUATION:
                kwargs = {"question": "Describe a challenge.", "candidate_answer": "..."}
            messages = prompts.build_task_messages(task, "rubric_json", config, **kwargs)
            system, user = messages[0]["content"], messages[1]["content"]
            # Neutral system prompt: mentions every profession, not this one.
            assert "every profession" in system.lower()
            assert role not in system  # role is data, not baked into the system prompt
            assert role in user  # the role adapts the prompt via the user message

    @pytest.mark.parametrize(
        "role,sector,level,types", PROFESSIONS, ids=PARAM_IDS
    )
    def test_evaluation_works_for_every_profession(
        self, role, sector, level, types
    ) -> None:
        client = FakeClient()
        service = EvaluationService(client, _pricing())
        settings = ModelSettings(model="openai/gpt-5-mini", prompt_technique="rubric_json")
        evaluation, usage = service.evaluate_answer(
            _config(role, sector, level, types),
            "Tell me about a difficult decision.",
            "I weighed the trade-offs and chose the safer option.",
            settings,
        )
        assert evaluation.overall_score == 70
        assert usage.total_tokens == 75
        assert role in client.roles_seen[0]  # role reached the user message
