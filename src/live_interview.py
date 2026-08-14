"""Real-time live-interview backend (Gemini Live, experimental).

Architecture principle: OpenRouter remains the authoritative interview
intelligence — questions, evaluation, Deep Dive and the final report all still
come from the existing services. Gemini Live is only the real-time
conversational/audio *interface*. This module therefore contains no second
interview engine; it:

* mints short-lived Gemini **ephemeral tokens** so the permanent key never
  reaches the browser (:class:`GeminiLiveTokenService`);
* provides the non-secret session configuration the browser component needs and
  delegates all substantive work to the OpenRouter services
  (:class:`LiveInterviewService`);
* models the live turn lifecycle as an explicit state machine
  (:class:`LiveInterviewSession`);
* bounds reconnection so a failing session can never loop forever
  (:class:`ReconnectPolicy`).

Privacy: neither the permanent key nor any token is ever logged.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from src import constants
from src.config import AppConfig
from src.models import ExternalServiceUsage

__all__ = [
    "LiveInterviewError",
    "LiveTurnState",
    "EphemeralToken",
    "LiveTranscriptEntry",
    "GeminiLiveTokenService",
    "LiveInterviewService",
    "LiveInterviewSession",
    "ReconnectPolicy",
]

_LOGGER = logging.getLogger(__name__)


class LiveInterviewError(Exception):
    """A controlled, user-safe live-interview failure (never contains secrets)."""

    def __init__(self, message: str, *, category: str = "live_error") -> None:
        super().__init__(message)
        self.message = message
        self.category = category


# --- Turn lifecycle ----------------------------------------------------------


class LiveTurnState(str, Enum):
    """Explicit states for one live interview turn (no loose booleans)."""

    PREPARING = "preparing"
    INTERVIEWER_SPEAKING = "interviewer_speaking"
    CANDIDATE_THINKING = "candidate_thinking"
    CANDIDATE_SPEAKING = "candidate_speaking"
    PROCESSING_TRANSCRIPT = "processing_transcript"
    EVALUATING = "evaluating"
    READY_FOR_NEXT = "ready_for_next"
    ERROR = "error"
    COMPLETE = "complete"


# Allowed transitions. Kept explicit so the flow is auditable and testable.
_ALLOWED: dict[LiveTurnState, set[LiveTurnState]] = {
    LiveTurnState.PREPARING: {
        LiveTurnState.INTERVIEWER_SPEAKING,
        LiveTurnState.ERROR,
    },
    LiveTurnState.INTERVIEWER_SPEAKING: {
        LiveTurnState.CANDIDATE_THINKING,
        LiveTurnState.CANDIDATE_SPEAKING,  # barge-in / interruption
        LiveTurnState.ERROR,
    },
    LiveTurnState.CANDIDATE_THINKING: {
        LiveTurnState.CANDIDATE_SPEAKING,
        LiveTurnState.COMPLETE,
        LiveTurnState.ERROR,
    },
    LiveTurnState.CANDIDATE_SPEAKING: {
        LiveTurnState.PROCESSING_TRANSCRIPT,
        LiveTurnState.ERROR,
    },
    LiveTurnState.PROCESSING_TRANSCRIPT: {
        LiveTurnState.EVALUATING,
        LiveTurnState.ERROR,
    },
    LiveTurnState.EVALUATING: {
        LiveTurnState.READY_FOR_NEXT,
        LiveTurnState.ERROR,
    },
    LiveTurnState.READY_FOR_NEXT: {
        LiveTurnState.PREPARING,  # next turn (main or Deep Dive)
        LiveTurnState.COMPLETE,
        LiveTurnState.ERROR,
    },
    LiveTurnState.ERROR: {
        LiveTurnState.PREPARING,  # recover / retry
        LiveTurnState.COMPLETE,
    },
    LiveTurnState.COMPLETE: set(),
}


@dataclass
class LiveTranscriptEntry:
    """One turn's transcript: canonical question, spoken text and the answer."""

    question: str
    question_id: int | None = None
    interviewer_spoken: str = ""
    candidate_transcript: str = ""
    started_at: float | None = None
    ended_at: float | None = None


class LiveInterviewSession:
    """Explicit state machine for the live turn lifecycle (framework-free).

    Holds the *canonical* question for the current turn (authored by OpenRouter),
    the transcript entries, and the interruption flags. Transitions are validated
    so an illegal move raises instead of silently corrupting state.
    """

    def __init__(self, *, clock: Callable[[], float] | None = None) -> None:
        self._clock = clock or time.time
        self.state: LiveTurnState = LiveTurnState.PREPARING
        self.entries: list[LiveTranscriptEntry] = []
        self.interrupted: bool = False
        # When True the browser must discard any not-yet-played interviewer audio.
        self.discard_stale_audio: bool = False
        self.error_message: str | None = None

    # -- low-level transition -------------------------------------------------

    def transition_to(self, new_state: LiveTurnState) -> None:
        if new_state not in _ALLOWED.get(self.state, set()):
            raise LiveInterviewError(
                f"Illegal live-turn transition {self.state.value} -> "
                f"{new_state.value}.",
                category="invalid_transition",
            )
        self.state = new_state

    # -- turn steps -----------------------------------------------------------

    @property
    def current(self) -> LiveTranscriptEntry | None:
        return self.entries[-1] if self.entries else None

    def begin_question(self, question: str, question_id: int | None = None) -> None:
        """Start a new turn with the canonical question (from OpenRouter)."""
        if self.state not in (
            LiveTurnState.PREPARING,
            LiveTurnState.READY_FOR_NEXT,
            LiveTurnState.ERROR,
        ):
            raise LiveInterviewError(
                f"Cannot begin a question from {self.state.value}.",
                category="invalid_transition",
            )
        if self.state != LiveTurnState.PREPARING:
            self.transition_to(LiveTurnState.PREPARING)
        self.entries.append(
            LiveTranscriptEntry(
                question=question, question_id=question_id, started_at=self._clock()
            )
        )
        self.interrupted = False
        self.discard_stale_audio = False

    def interviewer_speaking(self, spoken: str = "") -> None:
        self.transition_to(LiveTurnState.INTERVIEWER_SPEAKING)
        if self.current is not None and spoken:
            self.current.interviewer_spoken = spoken

    def candidate_thinking(self) -> None:
        self.transition_to(LiveTurnState.CANDIDATE_THINKING)

    def candidate_speaking(self) -> None:
        self.transition_to(LiveTurnState.CANDIDATE_SPEAKING)

    def interrupt(self) -> None:
        """Candidate barge-in: stop the interviewer and discard stale audio."""
        if self.state != LiveTurnState.INTERVIEWER_SPEAKING:
            raise LiveInterviewError(
                "Interruption is only valid while the interviewer is speaking.",
                category="invalid_transition",
            )
        self.interrupted = True
        self.discard_stale_audio = True
        self.transition_to(LiveTurnState.CANDIDATE_SPEAKING)

    def submit_transcript(self, transcript: str) -> None:
        """Record the candidate's transcript and move to processing."""
        self.transition_to(LiveTurnState.PROCESSING_TRANSCRIPT)
        if self.current is not None:
            self.current.candidate_transcript = transcript
            self.current.ended_at = self._clock()

    def evaluating(self) -> None:
        self.transition_to(LiveTurnState.EVALUATING)

    def ready_for_next(self) -> None:
        self.transition_to(LiveTurnState.READY_FOR_NEXT)

    def complete(self) -> None:
        self.transition_to(LiveTurnState.COMPLETE)

    def fail(self, message: str) -> None:
        """Enter the ERROR state with a safe message (recoverable)."""
        self.error_message = message
        self.state = LiveTurnState.ERROR  # ERROR is reachable from any state


# --- Ephemeral token ---------------------------------------------------------


@dataclass(frozen=True)
class EphemeralToken:
    """A short-lived Gemini Live token — the only credential the browser sees.

    The token string is masked in ``repr`` so it never lands in logs or error
    output by accident.
    """

    token: str
    expires_at: float
    model: str
    new_session_expires_at: float | None = None

    def is_expired(self, now: float) -> bool:
        return now >= self.expires_at

    def __repr__(self) -> str:  # pragma: no cover - trivial, but safety-critical
        return (
            f"EphemeralToken(token='***', expires_at={self.expires_at}, "
            f"model={self.model!r})"
        )


TokenMinter = Callable[..., dict[str, Any]]


class GeminiLiveTokenService:
    """Mints short-lived ephemeral tokens from the permanent Gemini key.

    The permanent key is used **only here, on the backend**, and is never
    returned, logged, or placed in any browser-bound payload. A token minter can
    be injected for testing; the default lazily uses the Google GenAI SDK.
    """

    provider = constants.LIVE_PROVIDER

    def __init__(
        self,
        config: AppConfig,
        *,
        token_minter: TokenMinter | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._token_minter = token_minter
        self._clock = clock or time.time

    @property
    def is_available(self) -> bool:
        return self._config.is_live_configured

    def create_ephemeral_token(
        self, *, ttl_seconds: int = constants.LIVE_EPHEMERAL_TOKEN_TTL_SECONDS
    ) -> EphemeralToken:
        """Return a fresh ephemeral token; expiry and renewal are explicit."""
        if not self.is_available or self._config.gemini_api_key is None:
            raise LiveInterviewError(
                "Live interview is not configured: no Gemini API key.",
                category="unavailable",
            )
        now = self._clock()
        minter = self._token_minter or self._default_minter
        try:
            minted = minter(
                api_key=self._config.gemini_api_key.get_secret_value(),
                model=self._config.gemini_live_model,
                ttl_seconds=ttl_seconds,
                now=now,
            )
        except LiveInterviewError:
            raise
        except Exception as exc:  # noqa: BLE001 - controlled, no token/key in message
            _LOGGER.warning(
                "ephemeral token minting failed: provider=%s error=%s",
                self.provider,
                type(exc).__name__,
            )
            raise LiveInterviewError(
                "Could not start the live interview. Please try again.",
                category="token_error",
            ) from exc

        token = minted.get("token")
        if not token:
            raise LiveInterviewError(
                "The token service returned no token.", category="token_error"
            )
        return EphemeralToken(
            token=token,
            expires_at=float(minted.get("expires_at", now + ttl_seconds)),
            model=self._config.gemini_live_model,
            new_session_expires_at=minted.get("new_session_expires_at"),
        )

    def _default_minter(
        self, *, api_key: str, model: str, ttl_seconds: int, now: float
    ) -> dict[str, Any]:  # pragma: no cover - requires the SDK + network
        try:
            from google import genai
        except ImportError as exc:
            raise LiveInterviewError(
                "The Google GenAI library is not installed.",
                category="unavailable",
            ) from exc
        client = genai.Client(
            api_key=api_key, http_options={"api_version": "v1alpha"}
        )
        created = client.auth_tokens.create(
            config={
                "uses": 1,
                "expire_time": now + ttl_seconds,
                "new_session_expire_time": now
                + constants.LIVE_NEW_SESSION_WINDOW_SECONDS,
                "live_connect_constraints": {"model": model},
            }
        )
        return {
            "token": getattr(created, "name", None) or getattr(created, "token", None),
            "expires_at": now + ttl_seconds,
            "new_session_expires_at": now
            + constants.LIVE_NEW_SESSION_WINDOW_SECONDS,
        }


# --- Reconnect policy --------------------------------------------------------


class ReconnectPolicy:
    """Bounded exponential backoff for live reconnects (never infinite)."""

    def __init__(
        self,
        *,
        max_reconnects: int = constants.LIVE_MAX_RECONNECTS,
        base_delay: float = constants.LIVE_RECONNECT_BASE_DELAY_SECONDS,
        max_delay: float = constants.LIVE_RECONNECT_MAX_DELAY_SECONDS,
    ) -> None:
        self.max_reconnects = max_reconnects
        self.base_delay = base_delay
        self.max_delay = max_delay

    def next_delay(self, attempt: int) -> float | None:
        """Delay before ``attempt`` (1-based), or None once the bound is passed."""
        if attempt < 1 or attempt > self.max_reconnects:
            return None
        return min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)


# --- Live interview service --------------------------------------------------


class LiveInterviewService:
    """Coordinates the live interface without owning interview intelligence.

    Every substantive step is delegated to the existing OpenRouter services, so
    there is exactly one interview engine. This service adds only the live
    concerns: minting a browser token, the non-secret session configuration, and
    separate Gemini usage accounting.
    """

    def __init__(
        self,
        *,
        token_service: GeminiLiveTokenService,
        interview_service: Any | None = None,
        evaluation_service: Any | None = None,
        report_service: Any | None = None,
    ) -> None:
        # start_session()/gemini_usage() only need the token service; the
        # OpenRouter services are required only for the delegation methods.
        self._interview = interview_service
        self._evaluation = evaluation_service
        self._report = report_service
        self._tokens = token_service

    @property
    def is_available(self) -> bool:
        return self._tokens.is_available

    def start_session(self) -> tuple[EphemeralToken, dict[str, Any]]:
        """Mint a token and return it with the non-secret browser config.

        The returned config never contains the permanent key — only the
        ephemeral token, model and audio parameters the component needs.
        """
        token = self._tokens.create_ephemeral_token()
        config = {
            "model": token.model,
            "ephemeral_token": token.token,
            "token_expires_at": token.expires_at,
            "input_sample_rate": constants.LIVE_AUDIO_SAMPLE_RATE,
            "output_sample_rate": constants.LIVE_AUDIO_OUTPUT_SAMPLE_RATE,
            "chunk_ms": constants.LIVE_AUDIO_CHUNK_MS,
            "max_reconnects": constants.LIVE_MAX_RECONNECTS,
        }
        return token, config

    # -- delegation to the authoritative OpenRouter services ------------------

    def next_question(self, *args: Any, **kwargs: Any):
        """Canonical next question — authored by OpenRouter, not Gemini."""
        return self._interview.generate_next_question(*args, **kwargs)

    def evaluate_transcript(self, config, question: str, transcript: str, settings):
        """The candidate's live transcript flows into the normal evaluator."""
        return self._evaluation.evaluate_answer(config, question, transcript, settings)

    def deep_dive_question(self, *args: Any, **kwargs: Any):
        """Deep Dive question — from the existing branching service, spoken live."""
        return self._interview.generate_branch_question(*args, **kwargs)

    # -- usage accounting (separate from OpenRouter) --------------------------

    @staticmethod
    def gemini_usage(session_seconds: float) -> ExternalServiceUsage:
        """Gemini Live usage as audio seconds; cost is never invented."""
        return ExternalServiceUsage(
            provider=constants.LIVE_PROVIDER,
            operation="live_interview",
            units=float(max(0.0, session_seconds)),
            unit_name="session_seconds",
            cost_usd=None,
            cost_source="unavailable",
        )
