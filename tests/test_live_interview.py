"""Tests for the live-interview backend (Gemini Live).

Token minting and all provider calls are mocked — no live Gemini calls. These
tests assert the security boundary (permanent key never leaves the backend), the
explicit turn state machine, bounded reconnect, delegation to the authoritative
OpenRouter services, and graceful failure.
"""

import json

import pytest
from pydantic import SecretStr

from src import constants
from src.config import AppConfig
from src.live_interview import (
    EphemeralToken,
    GeminiLiveTokenService,
    LiveInterviewError,
    LiveInterviewService,
    LiveInterviewSession,
    LiveTurnState,
    ReconnectPolicy,
)
from src.models import ExternalServiceUsage

PERMANENT_KEY = "PERMANENT-GEMINI-KEY-do-not-leak"


def _live_config() -> AppConfig:
    return AppConfig(
        gemini_api_key=SecretStr(PERMANENT_KEY), gemini_live_model="gemini-live-x"
    )


def _minter(**kwargs):
    # Mimics the SDK: receives the permanent key, returns only an ephemeral token.
    assert kwargs["api_key"] == PERMANENT_KEY  # backend uses the permanent key
    return {
        "token": "EPHEMERAL-TOKEN-abc",
        "expires_at": kwargs["now"] + kwargs["ttl_seconds"],
        "new_session_expires_at": kwargs["now"] + 60,
    }


def _token_service(config=None, minter=_minter, clock=lambda: 1000.0):
    return GeminiLiveTokenService(
        config or _live_config(), token_minter=minter, clock=clock
    )


# --- Token provisioning ------------------------------------------------------


class TestTokenService:
    def test_mints_ephemeral_token(self) -> None:
        token = _token_service().create_ephemeral_token(ttl_seconds=1800)
        assert isinstance(token, EphemeralToken)
        assert token.token == "EPHEMERAL-TOKEN-abc"
        assert token.expires_at == 1000.0 + 1800
        assert token.model == "gemini-live-x"

    def test_unavailable_without_key(self) -> None:
        service = GeminiLiveTokenService(AppConfig(), token_minter=_minter)
        assert service.is_available is False
        with pytest.raises(LiveInterviewError) as exc:
            service.create_ephemeral_token()
        assert exc.value.category == "unavailable"

    def test_minter_failure_is_controlled(self) -> None:
        def boom(**_kwargs):
            raise RuntimeError("network down")

        with pytest.raises(LiveInterviewError) as exc:
            _token_service(minter=boom).create_ephemeral_token()
        assert exc.value.category == "token_error"

    def test_token_repr_is_masked(self) -> None:
        token = _token_service().create_ephemeral_token()
        assert "EPHEMERAL-TOKEN-abc" not in repr(token)
        assert "***" in repr(token)

    def test_token_expiry_is_explicit(self) -> None:
        token = _token_service(clock=lambda: 500.0).create_ephemeral_token(
            ttl_seconds=100
        )
        assert token.is_expired(599.0) is False
        assert token.is_expired(600.0) is True


# --- Security boundary -------------------------------------------------------


class TestSecurityBoundary:
    def test_permanent_key_never_reaches_frontend_config(self) -> None:
        service = LiveInterviewService(token_service=_token_service())
        token, config = service.start_session()
        payload = json.dumps(config)
        # The browser config carries only the ephemeral token, never the key.
        assert PERMANENT_KEY not in payload
        assert config["ephemeral_token"] == "EPHEMERAL-TOKEN-abc"
        assert token.token == "EPHEMERAL-TOKEN-abc"
        assert "gemini_api_key" not in config

    def test_start_session_carries_audio_params(self) -> None:
        _token, config = LiveInterviewService(
            token_service=_token_service()
        ).start_session()
        assert config["input_sample_rate"] == constants.LIVE_AUDIO_SAMPLE_RATE
        assert config["chunk_ms"] == constants.LIVE_AUDIO_CHUNK_MS
        assert config["max_reconnects"] == constants.LIVE_MAX_RECONNECTS


# --- Turn state machine ------------------------------------------------------


class TestTurnStateMachine:
    def test_happy_path(self) -> None:
        session = LiveInterviewSession(clock=lambda: 1.0)
        session.begin_question("Tell me about a challenge.", 1)
        assert session.state is LiveTurnState.PREPARING
        session.interviewer_speaking("Tell me about a challenge.")
        session.candidate_thinking()
        session.candidate_speaking()
        session.submit_transcript("I handled a tough migration.")
        session.evaluating()
        session.ready_for_next()
        session.complete()
        assert session.state is LiveTurnState.COMPLETE
        assert session.current.candidate_transcript == "I handled a tough migration."

    def test_canonical_question_is_preserved(self) -> None:
        session = LiveInterviewSession(clock=lambda: 1.0)
        session.begin_question("CANONICAL-Q", 7)
        session.interviewer_speaking()
        session.candidate_speaking()
        session.submit_transcript("my answer")
        # The canonical question is untouched by the spoken interaction.
        assert session.current.question == "CANONICAL-Q"
        assert session.current.question_id == 7

    def test_illegal_transition_raises(self) -> None:
        session = LiveInterviewSession()
        with pytest.raises(LiveInterviewError) as exc:
            session.evaluating()  # not valid from PREPARING
        assert exc.value.category == "invalid_transition"

    def test_interruption_barge_in(self) -> None:
        session = LiveInterviewSession()
        session.begin_question("Q", 1)
        session.interviewer_speaking()
        session.interrupt()
        assert session.state is LiveTurnState.CANDIDATE_SPEAKING
        assert session.interrupted is True
        assert session.discard_stale_audio is True

    def test_interruption_only_while_speaking(self) -> None:
        session = LiveInterviewSession()
        session.begin_question("Q", 1)
        with pytest.raises(LiveInterviewError):
            session.interrupt()  # interviewer not speaking yet

    def test_error_is_reachable_and_recoverable(self) -> None:
        session = LiveInterviewSession()
        session.begin_question("Q", 1)
        session.interviewer_speaking()
        session.fail("connection lost")
        assert session.state is LiveTurnState.ERROR
        assert session.error_message == "connection lost"
        session.begin_question("Q2", 2)  # recover
        assert session.state is LiveTurnState.PREPARING

    def test_complete_is_terminal(self) -> None:
        session = LiveInterviewSession()
        session.begin_question("Q", 1)
        session.interviewer_speaking()
        session.candidate_thinking()
        session.complete()
        with pytest.raises(LiveInterviewError):
            session.interviewer_speaking()


# --- Reconnect policy --------------------------------------------------------


class TestReconnectPolicy:
    def test_bounded_and_backoff(self) -> None:
        policy = ReconnectPolicy(max_reconnects=3, base_delay=1.0, max_delay=8.0)
        assert policy.next_delay(1) == 1.0
        assert policy.next_delay(2) == 2.0
        assert policy.next_delay(3) == 4.0
        assert policy.next_delay(4) is None  # bound reached — no infinite loop
        assert policy.next_delay(0) is None

    def test_delay_is_capped(self) -> None:
        policy = ReconnectPolicy(max_reconnects=10, base_delay=1.0, max_delay=3.0)
        assert policy.next_delay(9) == 3.0


# --- Delegation to OpenRouter (single engine) --------------------------------


class _FakeInterview:
    def __init__(self):
        self.branch_args = None

    def generate_next_question(self, *args, **kwargs):
        return ("CANONICAL_QUESTION", "usage")

    def generate_branch_question(self, *args, **kwargs):
        self.branch_args = (args, kwargs)
        return ("DEEP_DIVE_QUESTION", "usage")


class _FakeEvaluation:
    def __init__(self):
        self.received = None

    def evaluate_answer(self, config, question, transcript, settings):
        self.received = {"question": question, "transcript": transcript}
        return ("EVALUATION", "usage")


class TestDelegation:
    def test_next_question_comes_from_openrouter(self) -> None:
        service = LiveInterviewService(
            token_service=_token_service(), interview_service=_FakeInterview()
        )
        assert service.next_question() == ("CANONICAL_QUESTION", "usage")

    def test_transcript_is_passed_to_evaluator(self) -> None:
        evaluation = _FakeEvaluation()
        service = LiveInterviewService(
            token_service=_token_service(), evaluation_service=evaluation
        )
        service.evaluate_transcript(
            {}, "the question", "the spoken transcript", {}
        )
        assert evaluation.received["transcript"] == "the spoken transcript"

    def test_deep_dive_uses_branching_service(self) -> None:
        interview = _FakeInterview()
        service = LiveInterviewService(
            token_service=_token_service(), interview_service=interview
        )
        assert service.deep_dive_question(depth=1) == ("DEEP_DIVE_QUESTION", "usage")
        assert interview.branch_args is not None

    def test_gemini_usage_is_separate_and_unpriced(self) -> None:
        usage = LiveInterviewService.gemini_usage(42.0)
        assert isinstance(usage, ExternalServiceUsage)
        assert usage.provider == constants.LIVE_PROVIDER
        assert usage.units == 42.0
        assert usage.cost_usd is None
        assert usage.cost_source == "unavailable"


# --- Availability / fallback -------------------------------------------------


class TestAvailability:
    def test_service_unavailable_without_key(self) -> None:
        service = LiveInterviewService(
            token_service=GeminiLiveTokenService(AppConfig())
        )
        assert service.is_available is False

    def test_start_session_fails_without_key(self) -> None:
        service = LiveInterviewService(
            token_service=GeminiLiveTokenService(AppConfig())
        )
        with pytest.raises(LiveInterviewError):
            service.start_session()


# --- 1E: token refresh decision (mint only when needed) ---------------------


class TestTokenRefreshDecision:
    def test_valid_token_is_reused(self):
        from src.live_interview import token_needs_refresh

        assert token_needs_refresh(10_000_000_000.0, now=1000.0) is False

    def test_expired_token_needs_refresh(self):
        from src.live_interview import token_needs_refresh

        assert token_needs_refresh(100.0, now=1000.0) is True

    def test_within_skew_needs_refresh(self):
        from src.live_interview import token_needs_refresh

        # 980 is within 30s of a 1000 expiry → refresh proactively.
        assert token_needs_refresh(1000.0, now=980.0, skew_seconds=30.0) is True
        assert token_needs_refresh(1000.0, now=960.0, skew_seconds=30.0) is False

    def test_absent_expiry_needs_refresh(self):
        from src.live_interview import token_needs_refresh

        assert token_needs_refresh(0.0, now=1000.0) is True
