"""Tests for the speech-to-text service.

Every speech API call is mocked with an injected fake client — no Google SDK,
no credentials and no network are required. Audio is synthesised locally.
"""

import io
import json
import logging
import wave
from types import SimpleNamespace

import pytest

from src import constants
from src.models import ExternalServiceUsage
from src.speech_service import (
    GoogleSpeechTranscriptionService,
    SpeechError,
    UnavailableSpeechService,
    audio_duration_seconds,
    build_speech_service,
    compute_voice_metrics,
    transcribe_recording,
    validate_audio,
)

PROVIDER = constants.SPEECH_PROVIDER_GOOGLE


def _wav_bytes(seconds: float, rate: int = 16_000) -> bytes:
    """Return a minimal mono 16-bit PCM WAV of the given duration."""
    frames = int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * frames)
    return buffer.getvalue()


def _response(pairs) -> SimpleNamespace:
    """Build a fake Speech V2 response from (transcript, confidence, language)."""
    results = []
    for transcript, confidence, language in pairs:
        alt = SimpleNamespace(transcript=transcript, confidence=confidence)
        results.append(SimpleNamespace(alternatives=[alt], language_code=language))
    return SimpleNamespace(results=results)


class FakeSpeechClient:
    def __init__(self, response=None, error=None, streaming_response=None):
        self._response = response
        self._error = error
        self._streaming_response = streaming_response
        self.requests: list[dict] = []
        self.sync_calls = 0
        self.streaming_calls = 0

    def recognize(self, request):
        self.sync_calls += 1
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._response

    def streaming_recognize(self, requests):
        self.streaming_calls += 1
        # Consume the generator so request construction is exercised.
        list(requests)
        if self._error is not None:
            raise self._error
        # A streaming call yields a sequence of responses.
        return self._streaming_response or []


def _service(response=None, error=None) -> GoogleSpeechTranscriptionService:
    return GoogleSpeechTranscriptionService(
        project_id="test-project",
        client=FakeSpeechClient(response=response, error=error),
    )


def _service_streaming(streaming_response) -> GoogleSpeechTranscriptionService:
    return GoogleSpeechTranscriptionService(
        project_id="test-project",
        client=FakeSpeechClient(streaming_response=streaming_response),
    )


# --- Audio validation --------------------------------------------------------


class TestAudioValidation:
    def test_duration_of_wav(self) -> None:
        assert abs(audio_duration_seconds(_wav_bytes(2.0), "audio/wav") - 2.0) < 0.05

    def test_empty_recording_rejected(self) -> None:
        with pytest.raises(SpeechError) as exc:
            validate_audio(b"", "audio/wav")
        assert exc.value.category == "empty"

    def test_unsupported_mime_rejected(self) -> None:
        with pytest.raises(SpeechError) as exc:
            validate_audio(_wav_bytes(0.1), "application/pdf")
        assert exc.value.category == "unsupported_mime"

    def test_oversized_recording_rejected(self) -> None:
        with pytest.raises(SpeechError) as exc:
            validate_audio(b"\x00" * 50, "audio/wav", max_bytes=10)
        assert exc.value.category == "too_large"

    def test_over_length_recording_rejected(self) -> None:
        with pytest.raises(SpeechError) as exc:
            validate_audio(_wav_bytes(2.0), "audio/wav", max_seconds=1)
        assert exc.value.category == "too_long"


class TestVoiceMetrics:
    def test_metrics_include_wpm(self) -> None:
        metrics = compute_voice_metrics("one two three four", 60.0)
        assert metrics["word_count"] == 4
        assert metrics["duration_seconds"] == 60.0
        assert metrics["words_per_minute"] == 4.0

    def test_wpm_none_without_duration(self) -> None:
        metrics = compute_voice_metrics("hello world", None)
        assert metrics["word_count"] == 2
        assert metrics["words_per_minute"] is None


# --- Google provider ---------------------------------------------------------


class TestGoogleProvider:
    def test_recording_becomes_transcript(self) -> None:
        service = _service(_response([("Hello world", 0.9, "en-US")]))
        result = service.transcribe(
            _wav_bytes(1.0), mime_type="audio/wav", language="en-US"
        )
        assert result.transcript == "Hello world"
        assert result.detected_language == "en-US"
        assert result.provider == PROVIDER
        assert result.quality["average_confidence"] == 0.9

    def test_request_carries_language_and_model(self) -> None:
        service = _service(_response([("Hi", 0.8, "en-US")]))
        service.transcribe(_wav_bytes(0.5), mime_type="audio/wav", language="en-US")
        request = service._client.requests[0]
        assert request["config"]["language_codes"] == ["en-US"]
        assert request["config"]["model"] == constants.SPEECH_MODEL_CHIRP3
        assert "content" in request  # audio sent, not persisted

    def test_auto_language_when_unset(self) -> None:
        service = _service(_response([("Hallo", 0.7, "de-DE")]))
        service.transcribe(_wav_bytes(0.5), mime_type="audio/wav", language=None)
        assert service._client.requests[0]["config"]["language_codes"] == ["auto"]

    def test_transcription_is_verbatim_not_rewritten(self) -> None:
        # The provider text is preserved exactly (mistakes and all).
        raw = "um i i think we we should of done it"
        service = _service(_response([(raw, 0.6, "en-US")]))
        result = service.transcribe(_wav_bytes(1.0), mime_type="audio/wav")
        assert result.transcript == raw

    def test_provider_error_is_controlled(self) -> None:
        service = _service(error=RuntimeError("boom"))
        with pytest.raises(SpeechError) as exc:
            service.transcribe(_wav_bytes(0.5), mime_type="audio/wav")
        assert exc.value.category == "provider_error"

    def test_blank_transcript_rejected(self) -> None:
        service = _service(_response([]))
        with pytest.raises(SpeechError) as exc:
            service.transcribe(_wav_bytes(0.5), mime_type="audio/wav")
        assert exc.value.category == "empty_transcript"

    def test_unsupported_audio_rejected_before_call(self) -> None:
        service = _service(_response([("x", 0.9, "en-US")]))
        with pytest.raises(SpeechError):
            service.transcribe(_wav_bytes(0.5), mime_type="application/pdf")
        assert service._client.requests == []  # no API call made


# --- Short vs long recordings (sync vs streaming) ----------------------------


class TestRecordingLength:
    def test_short_recording_uses_sync_recognize(self) -> None:
        service = _service(_response([("A short answer.", 0.9, "en-US")]))
        result = service.transcribe(_wav_bytes(3.0), mime_type="audio/wav")
        assert result.transcript == "A short answer."
        assert service._client.sync_calls == 1
        assert service._client.streaming_calls == 0

    def test_long_recording_uses_streaming(self) -> None:
        # Over the ~55 s threshold → streaming API (aggregates final results).
        streaming = [
            _response([("This is the first part", 0.9, "en-US")]),
            _response([("and this is the second part.", 0.85, "en-US")]),
        ]
        service = _service_streaming(streaming)
        result = service.transcribe(_wav_bytes(70.0), mime_type="audio/wav")
        assert "first part" in result.transcript
        assert "second part" in result.transcript
        assert service._client.streaming_calls == 1
        assert service._client.sync_calls == 0

    def test_long_recording_within_ten_minute_maximum(self) -> None:
        # 9 minutes is allowed via streaming; over 10 minutes is still rejected.
        service = _service_streaming([_response([("ok", 0.9, "en-US")])])
        result = service.transcribe(_wav_bytes(540.0), mime_type="audio/wav")
        assert result.transcript == "ok"
        with pytest.raises(SpeechError) as exc:
            service.transcribe(_wav_bytes(700.0), mime_type="audio/wav")
        assert exc.value.category == "too_long"


# --- Availability / factory --------------------------------------------------


class TestAvailability:
    def test_missing_project_yields_unavailable(self) -> None:
        config = SimpleNamespace(google_speech_project_id=None)
        service = build_speech_service(config)
        assert isinstance(service, UnavailableSpeechService)
        assert service.is_available is False

    def test_configured_project_yields_google(self) -> None:
        config = SimpleNamespace(
            google_speech_project_id="p", google_speech_location="global"
        )
        service = build_speech_service(config)
        assert isinstance(service, GoogleSpeechTranscriptionService)
        assert service.is_available is True

    def test_unavailable_service_raises_on_transcribe(self) -> None:
        with pytest.raises(SpeechError) as exc:
            UnavailableSpeechService().transcribe(b"x", mime_type="audio/wav")
        assert exc.value.category == "unavailable"


# --- End-to-end helper + privacy ---------------------------------------------


class TestTranscribeRecording:
    def test_returns_result_metrics_and_usage(self) -> None:
        service = _service(_response([("Hi there friend", 0.85, "en-US")]))
        result, metrics, usage = transcribe_recording(
            service, _wav_bytes(2.0), mime_type="audio/wav", language="en-US"
        )
        assert result.transcript == "Hi there friend"
        assert metrics["word_count"] == 3
        assert metrics["duration_seconds"] is not None
        assert isinstance(usage, ExternalServiceUsage)
        assert usage.operation == "speech_to_text"
        assert usage.unit_name == "audio_seconds"
        # Pricing is never invented.
        assert usage.cost_usd is None
        assert usage.cost_source == "unavailable"

    def test_no_audio_bytes_are_retained(self) -> None:
        service = _service(_response([("hello", 0.9, "en-US")]))
        audio = _wav_bytes(1.0)
        result, metrics, usage = transcribe_recording(
            service, audio, mime_type="audio/wav", language="en-US"
        )
        # Nothing returned carries raw audio; everything is text/number metadata.
        blob = json.dumps(
            {
                "transcript": result.transcript,
                "metrics": metrics,
                "usage": usage.model_dump(),
                "quality": result.quality,
            },
            default=str,
        )
        assert "\\x00" not in blob
        # The provider object does not stash the audio either.
        assert not any(
            isinstance(getattr(service, name, None), (bytes, bytearray))
            for name in vars(service)
        )

    def test_error_logs_no_audio_or_transcript_content(self, caplog) -> None:
        service = _service(error=RuntimeError("boom-secret-detail"))
        with caplog.at_level(logging.WARNING):
            with pytest.raises(SpeechError):
                service.transcribe(_wav_bytes(0.5), mime_type="audio/wav")
        blob = " ".join(record.getMessage() for record in caplog.records)
        assert "boom-secret-detail" not in blob  # raw error detail not logged
        assert PROVIDER in blob  # safe provider tag is fine
