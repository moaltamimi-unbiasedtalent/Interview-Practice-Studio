"""Manual live-API smoke suite (chargeable — explicit confirmation required).

Verifies real connectivity to the paid providers without exposing credentials.
Nothing runs by default: each check requires ``--confirm`` plus the provider
flag. Values (keys, tokens, transcripts) are never printed — only PASS/FAIL and
safe metadata.

Usage:
  python scripts/manual_live_check.py                 # dry run, no calls
  python scripts/manual_live_check.py --openrouter --confirm
  python scripts/manual_live_check.py --speech --confirm
  python scripts/manual_live_check.py --gemini --confirm
  python scripts/manual_live_check.py --all --confirm
"""

from __future__ import annotations

import argparse
import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402


def _short_silent_wav(seconds: float = 1.0, rate: int = 16_000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(b"\x00\x00" * int(seconds * rate))
    return buffer.getvalue()


def check_openrouter(config) -> str:
    if not config.is_configured:
        return "SKIP (OpenRouter not configured)"
    from src.openrouter_client import OpenRouterClient, OpenRouterError
    from src.pricing_service import PricingService

    client = OpenRouterClient(config)
    try:
        supported = None
        try:
            supported = list(PricingService().supported_parameters(config.model))
        except Exception:
            supported = None
        result = client.test_connection(supported_parameters=supported)
        return f"PASS (model reachable, request_id={result.request_id})"
    except OpenRouterError as exc:
        return f"FAIL ({exc.category})"
    finally:
        client.close()


def check_speech(config) -> str:
    if not config.is_speech_configured:
        return "SKIP (Speech not configured)"
    from src.speech_service import SpeechError, build_speech_service

    service = build_speech_service(config)
    try:
        result = service.transcribe(
            _short_silent_wav(), mime_type="audio/wav", language="en-US"
        )
        return f"PASS (transcribed {result.duration_seconds}s)"
    except SpeechError as exc:
        # An empty transcript on silence still proves the service is reachable.
        if exc.category == "empty_transcript":
            return "PASS (reachable; no speech in silent clip)"
        return f"FAIL ({exc.category})"


def check_gemini(config) -> str:
    if not config.is_live_configured:
        return "SKIP (Gemini not configured)"
    from src.live_interview import GeminiLiveTokenService, LiveInterviewError

    service = GeminiLiveTokenService(config)
    try:
        token = service.create_ephemeral_token()
        # Never print the token; report only that one was minted and its expiry.
        return f"PASS (ephemeral token minted, expires_at={token.expires_at:.0f})"
    except LiveInterviewError as exc:
        return f"FAIL ({exc.category})"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual live-API smoke suite.")
    parser.add_argument("--openrouter", action="store_true")
    parser.add_argument("--speech", action="store_true")
    parser.add_argument("--gemini", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)

    want_openrouter = args.openrouter or args.all
    want_speech = args.speech or args.all
    want_gemini = args.gemini or args.all

    if not args.confirm:
        print("DRY RUN — no chargeable requests made.")
        print("Re-run with the provider flag AND --confirm to make real calls:")
        print("  --openrouter : one tiny OpenRouter connection test")
        print("  --speech     : one short Speech-to-Text request (silent clip)")
        print("  --gemini     : mint one Gemini ephemeral token")
        return 0

    config = load_config()
    print("Manual live check (credentials never displayed):")
    if want_openrouter:
        print(f"  OpenRouter: {check_openrouter(config)}")
    if want_speech:
        print(f"  Speech-to-Text: {check_speech(config)}")
    if want_gemini:
        print(f"  Gemini Live token: {check_gemini(config)}")
    if not (want_openrouter or want_speech or want_gemini):
        print("  (no provider selected)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
