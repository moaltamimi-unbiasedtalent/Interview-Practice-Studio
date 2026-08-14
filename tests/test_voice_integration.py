"""Voice-answer integration: session accounting + transcript into evaluation.

All model and speech calls are mocked. Confirms a spoken answer's transcript is
handled exactly like a typed answer by the existing evaluation pipeline, and
that speech usage/metrics are recorded separately from LLM cost.
"""

import io
import json
import wave

from src.evaluation_service import EvaluationService
from src.models import (
    AnswerEvaluation,
    ExternalServiceUsage,
    InterviewConfiguration,
    ModelSettings,
)
from src.openrouter_client import ChatResult
from src.pricing_service import PricingService
from src.session_manager import SessionManager
from src.speech_service import GoogleSpeechTranscriptionService, transcribe_recording

MODEL = "openai/gpt-5-mini"


# --- helpers -----------------------------------------------------------------


def _wav_bytes(seconds: float, rate: int = 16_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


class _FakeSpeechClient:
    def recognize(self, request):
        from types import SimpleNamespace

        alt = SimpleNamespace(transcript="I led a team through a tough migration", confidence=0.9)
        return SimpleNamespace(
            results=[SimpleNamespace(alternatives=[alt], language_code="en-US")]
        )


class _FakeLLMClient:
    def __init__(self, contents):
        self._contents = list(contents)
        self.calls: list[dict] = []

    def create_chat_completion(self, **kwargs) -> ChatResult:
        self.calls.append(kwargs)
        return ChatResult(
            content=self._contents.pop(0),
            model=kwargs["model"],
            prompt_tokens=80,
            completion_tokens=40,
            total_tokens=120,
            reported_cost=None,
            duration_seconds=0.3,
            request_id="gen",
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


def _evaluation_json() -> str:
    return json.dumps(
        {
            "overall_score": 74,
            "relevance": 8,
            "structure": 7,
            "evidence": 7,
            "role_knowledge": 7,
            "problem_solving": 7,
            "communication": 8,
            "credibility": 7,
            "strengths": ["clear delivery"],
            "improvement_areas": ["add a metric"],
            "missing_evidence": ["numbers"],
            "stronger_answer_structure": "STAR",
            "improved_example_answer": "Example.",
            "follow_up_question": "What was the impact?",
        }
    )


def _transcript() -> str:
    service = GoogleSpeechTranscriptionService(
        project_id="p", client=_FakeSpeechClient()
    )
    result, _metrics, _usage = transcribe_recording(
        service, _wav_bytes(3.0), mime_type="audio/wav", language="en-US"
    )
    return result.transcript


# --- session accounting ------------------------------------------------------


class TestSessionVoiceAccounting:
    def test_transcription_usage_without_cost_not_added_to_total(self) -> None:
        manager = SessionManager({}, clock=lambda: 1.0)
        manager.record_transcription_usage(
            ExternalServiceUsage(
                provider="google_chirp3",
                operation="speech_to_text",
                units=5.0,
                unit_name="audio_seconds",
            )
        )
        assert len(manager.data.transcription_usage) == 1
        assert manager.data.cumulative_cost_usd == 0.0  # unpriced → not counted

    def test_transcription_usage_with_cost_added_to_total(self) -> None:
        manager = SessionManager({}, clock=lambda: 1.0)
        manager.record_transcription_usage(
            ExternalServiceUsage(
                provider="google_chirp3",
                operation="speech_to_text",
                units=5.0,
                unit_name="audio_seconds",
                cost_usd=0.02,
                cost_source="calculated",
            )
        )
        assert manager.data.cumulative_cost_usd == 0.02

    def test_voice_metrics_are_stored(self) -> None:
        manager = SessionManager({}, clock=lambda: 1.0)
        manager.record_voice_metrics({"word_count": 12, "words_per_minute": 110.0})
        assert manager.data.voice_metrics[0]["word_count"] == 12


# --- transcript into the evaluation pipeline ---------------------------------


class TestTranscriptEvaluation:
    def test_spoken_answer_is_evaluated_like_a_typed_answer(self) -> None:
        transcript = _transcript()
        client = _FakeLLMClient([_evaluation_json()])
        service = EvaluationService(client, _pricing())
        evaluation, _ = service.evaluate_answer(
            _config(), "Describe a challenge.", transcript, _settings()
        )
        assert isinstance(evaluation, AnswerEvaluation)
        # The transcript reaches the model as the candidate answer, verbatim.
        user_message = client.calls[0]["messages"][1]["content"]
        assert transcript in user_message

    def test_spoken_deep_dive_answer_is_evaluated(self) -> None:
        # A Deep Dive answer is evaluated through the same evaluate_answer path,
        # so a spoken transcript works there too.
        transcript = _transcript()
        client = _FakeLLMClient([_evaluation_json()])
        service = EvaluationService(client, _pricing())
        evaluation, _ = service.evaluate_answer(
            _config(), "Go deeper: why that approach?", transcript, _settings()
        )
        assert isinstance(evaluation, AnswerEvaluation)
        assert transcript in client.calls[0]["messages"][1]["content"]
