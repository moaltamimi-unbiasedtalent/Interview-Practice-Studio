"""Speech-to-text transcription (provider-agnostic).

The interview services never talk to a speech provider directly. They depend on
the small :class:`SpeechTranscriptionService` interface, so a new provider can be
added later without touching the interview pipeline or ``app.py``.

The first provider is Google Cloud Speech-to-Text V2 (Chirp 3). The Google SDK
and credentials are optional: when they are absent the app degrades to an
:class:`UnavailableSpeechService` and the text interview keeps working.

Privacy: this module never persists raw audio and never logs audio bytes or
transcript content. Audio is passed in as bytes, transcribed, and discarded.
"""

from __future__ import annotations

import io
import logging
import wave
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from src import constants
from src.models import ExternalServiceUsage

__all__ = [
    "TranscriptionResult",
    "SpeechError",
    "SpeechTranscriptionService",
    "UnavailableSpeechService",
    "GoogleSpeechTranscriptionService",
    "build_speech_service",
    "audio_duration_seconds",
    "validate_audio",
    "compute_voice_metrics",
    "transcribe_recording",
]

_LOGGER = logging.getLogger(__name__)


# --- Result and error types --------------------------------------------------


@dataclass(frozen=True)
class TranscriptionResult:
    """The plain, verbatim outcome of transcribing one recording.

    ``transcript`` is exactly what the candidate said — never rewritten,
    "improved" or corrected — so the evaluator assesses the real answer.
    """

    transcript: str
    detected_language: str | None
    duration_seconds: float | None
    quality: dict[str, float] | None
    provider: str


class SpeechError(Exception):
    """A controlled, user-safe speech-transcription failure.

    ``message`` is safe to display; ``category`` is a short machine-readable tag
    (e.g. ``"unavailable"``, ``"empty"``, ``"too_long"``) and never contains
    audio or transcript content.
    """

    def __init__(self, message: str, *, category: str = "speech_error") -> None:
        super().__init__(message)
        self.message = message
        self.category = category


# --- Audio helpers -----------------------------------------------------------


def audio_duration_seconds(data: bytes, mime_type: str) -> float | None:
    """Return the duration of WAV/PCM audio in seconds, or None if unknown.

    Only WAV is parsed (Streamlit's audio input returns WAV); other formats
    return None and are bounded by the byte-size limit instead.
    """
    if not data:
        return None
    if "wav" not in (mime_type or "").lower() and "wave" not in (mime_type or "").lower():
        return None
    try:
        with wave.open(io.BytesIO(data), "rb") as handle:
            frames = handle.getnframes()
            rate = handle.getframerate()
            if rate <= 0:
                return None
            return frames / float(rate)
    except (wave.Error, EOFError, ValueError):
        return None


def validate_audio(
    data: bytes,
    mime_type: str,
    *,
    max_bytes: int = constants.SPEECH_MAX_AUDIO_BYTES,
    max_seconds: int = constants.SPEECH_MAX_AUDIO_SECONDS,
    allowed_mime: Sequence[str] = constants.SPEECH_ALLOWED_MIME_TYPES,
) -> float | None:
    """Validate a recording before transcription; return its duration if known.

    Raises :class:`SpeechError` for an empty recording, an unsupported MIME
    type, an oversized file, or an over-length recording.
    """
    if not data:
        raise SpeechError(
            "The recording is empty. Please record your answer and try again.",
            category="empty",
        )
    normalised = (mime_type or "").split(";")[0].strip().lower()
    if normalised not in allowed_mime:
        raise SpeechError(
            "That audio format is not supported for transcription.",
            category="unsupported_mime",
        )
    if len(data) > max_bytes:
        raise SpeechError(
            "The recording is too large. Please record a shorter answer.",
            category="too_large",
        )
    duration = audio_duration_seconds(data, normalised)
    if duration is not None and duration > max_seconds:
        minutes = max_seconds // 60
        raise SpeechError(
            f"The recording is longer than the {minutes}-minute maximum. "
            "Please record a shorter answer.",
            category="too_long",
        )
    return duration


def compute_voice_metrics(
    transcript: str, duration_seconds: float | None
) -> dict[str, Any]:
    """Delivery metrics for the timing/coaching phase (not scored here).

    Returns audio duration, transcript word count and words-per-minute (only
    when a positive duration is known).
    """
    word_count = len(transcript.split())
    words_per_minute: float | None = None
    if duration_seconds and duration_seconds > 0:
        words_per_minute = round(word_count / (duration_seconds / 60.0), 1)
    return {
        "duration_seconds": (
            round(duration_seconds, 2) if duration_seconds else None
        ),
        "word_count": word_count,
        "words_per_minute": words_per_minute,
    }


# --- Service interface -------------------------------------------------------


class SpeechTranscriptionService(ABC):
    """Provider-agnostic transcription interface."""

    provider_name: str = "speech"

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Whether transcription is configured and can be attempted."""

    @abstractmethod
    def transcribe(
        self, data: bytes, *, mime_type: str, language: str | None = None
    ) -> TranscriptionResult:
        """Transcribe recorded audio into a verbatim :class:`TranscriptionResult`."""


class UnavailableSpeechService(SpeechTranscriptionService):
    """Used when no speech provider is configured; keeps the app crash-free."""

    provider_name = "unavailable"

    @property
    def is_available(self) -> bool:
        return False

    def transcribe(
        self, data: bytes, *, mime_type: str, language: str | None = None
    ) -> TranscriptionResult:
        raise SpeechError(
            "Voice answers are not available: speech-to-text is not configured. "
            "You can still type your answer.",
            category="unavailable",
        )


class GoogleSpeechTranscriptionService(SpeechTranscriptionService):
    """Google Cloud Speech-to-Text V2 (Chirp 3) provider.

    The Google client is created lazily and authenticated with Application
    Default Credentials, so importing this module never requires the SDK or
    credentials. A client can be injected for testing.
    """

    provider_name = constants.SPEECH_PROVIDER_GOOGLE

    def __init__(
        self,
        *,
        project_id: str,
        location: str = constants.SPEECH_LOCATION_DEFAULT,
        recognizer: str = "_",
        model: str = constants.SPEECH_MODEL_CHIRP3,
        default_language_codes: Sequence[str] = constants.SPEECH_DEFAULT_LANGUAGE_CODES,
        client: Any | None = None,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._project_id = project_id
        self._location = location
        self._recognizer = recognizer
        self._model = model
        self._default_language_codes = tuple(default_language_codes)
        self._client = client
        self._client_factory = client_factory

    @property
    def is_available(self) -> bool:
        return bool(self._project_id)

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:  # Lazy import so the SDK stays optional.
            from google.cloud.speech_v2 import SpeechClient
        except ImportError as exc:  # pragma: no cover - depends on optional dep
            raise SpeechError(
                "The Google Speech-to-Text library is not installed.",
                category="unavailable",
            ) from exc
        self._client = SpeechClient()
        return self._client

    def _recognizer_path(self) -> str:
        return (
            f"projects/{self._project_id}/locations/{self._location}"
            f"/recognizers/{self._recognizer}"
        )

    def _language_codes(self, language: str | None) -> list[str]:
        if language and language != "auto":
            return [language]
        # "auto" (or unset): let the model detect the language where supported.
        return ["auto"]

    def transcribe(
        self, data: bytes, *, mime_type: str, language: str | None = None
    ) -> TranscriptionResult:
        duration = validate_audio(data, mime_type)
        request = {
            "recognizer": self._recognizer_path(),
            "config": {
                "auto_decoding_config": {},
                "model": self._model,
                "language_codes": self._language_codes(language),
            },
            "content": data,
        }
        try:
            client = self._get_client()
            response = client.recognize(request=request)
        except SpeechError:
            raise
        except Exception as exc:  # noqa: BLE001 - controlled, message is safe
            # Log category only — never audio bytes or transcript content.
            _LOGGER.warning(
                "speech transcription failed: provider=%s error=%s",
                self.provider_name,
                type(exc).__name__,
            )
            raise SpeechError(
                "Transcription failed. Please try again or type your answer.",
                category="provider_error",
            ) from exc

        return self._map_response(response, duration, language)

    def _map_response(
        self, response: Any, duration: float | None, language: str | None
    ) -> TranscriptionResult:
        parts: list[str] = []
        languages: list[str] = []
        confidences: list[float] = []
        for result in getattr(response, "results", []) or []:
            alternatives = getattr(result, "alternatives", None) or []
            if not alternatives:
                continue
            best = alternatives[0]
            text = getattr(best, "transcript", "") or ""
            if text:
                parts.append(text.strip())
            lang = getattr(result, "language_code", None)
            if lang:
                languages.append(lang)
            confidence = getattr(best, "confidence", None)
            if isinstance(confidence, (int, float)) and confidence > 0:
                confidences.append(float(confidence))

        transcript = " ".join(part for part in parts if part).strip()
        if not transcript:
            raise SpeechError(
                "No speech was detected in the recording. Please record again "
                "or type your answer.",
                category="empty_transcript",
            )

        detected = languages[0] if languages else (language if language and language != "auto" else None)
        quality = (
            {"average_confidence": round(sum(confidences) / len(confidences), 4)}
            if confidences
            else None
        )
        return TranscriptionResult(
            transcript=transcript,
            detected_language=detected,
            duration_seconds=round(duration, 2) if duration else None,
            quality=quality,
            provider=self.provider_name,
        )


def transcribe_recording(
    service: SpeechTranscriptionService,
    data: bytes,
    *,
    mime_type: str,
    language: str | None = None,
) -> tuple[TranscriptionResult, dict[str, Any], ExternalServiceUsage]:
    """Transcribe a recording and return ``(result, metrics, usage)``.

    A single testable entry point for the UI: it never persists the audio and
    returns only text and numbers. Transcription cost is recorded as usage in
    audio seconds with ``cost_source="unavailable"`` — a real dollar cost is
    never invented (see :class:`~src.models.ExternalServiceUsage`).
    """
    result = service.transcribe(data, mime_type=mime_type, language=language)
    metrics = compute_voice_metrics(result.transcript, result.duration_seconds)
    usage = ExternalServiceUsage(
        provider=result.provider,
        operation="speech_to_text",
        units=float(result.duration_seconds or 0.0),
        unit_name="audio_seconds",
        cost_usd=None,
        cost_source="unavailable",
    )
    return result, metrics, usage


def build_speech_service(config: Any) -> SpeechTranscriptionService:
    """Return the configured speech provider, or an unavailable one.

    Uses ``config.google_speech_project_id`` to decide; credentials themselves
    come from Application Default Credentials and are never read here.
    """
    project_id = getattr(config, "google_speech_project_id", None)
    if project_id:
        return GoogleSpeechTranscriptionService(
            project_id=project_id,
            location=getattr(
                config, "google_speech_location", constants.SPEECH_LOCATION_DEFAULT
            ),
        )
    return UnavailableSpeechService()
