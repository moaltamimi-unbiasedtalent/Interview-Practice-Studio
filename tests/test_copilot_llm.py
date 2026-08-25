"""Foundation tests for the OpenRouter chat-model factory (no network calls)."""

import pytest
from pydantic import SecretStr

from src.copilot import constants
from src.copilot.config import CopilotConfig
from src.copilot.llm.openrouter import (
    CopilotConfigError,
    build_chat_model,
    default_model_kwargs,
)


class _FakeChatOpenAI:
    """Captures constructor kwargs instead of creating a real client."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _config(**over) -> CopilotConfig:
    base = dict(api_key=SecretStr("test-key-not-real"))
    base.update(over)
    return CopilotConfig(**base)


class TestFactory:
    def test_raises_without_api_key(self) -> None:
        with pytest.raises(CopilotConfigError):
            build_chat_model(CopilotConfig())

    def test_default_model_kwargs_have_no_secret(self) -> None:
        kwargs = default_model_kwargs(_config())
        assert kwargs["model"] == constants.DEFAULT_MODEL
        assert kwargs["base_url"] == constants.OPENROUTER_BASE_URL
        assert kwargs["timeout"] == constants.READ_TIMEOUT_SECONDS
        assert "api_key" not in kwargs  # secret is never in the kwargs dict

    def test_builds_with_injected_class_and_passes_key_directly(self) -> None:
        model = build_chat_model(
            _config(), model="openai/gpt-5", chat_openai_cls=_FakeChatOpenAI
        )
        assert isinstance(model, _FakeChatOpenAI)
        assert model.kwargs["model"] == "openai/gpt-5"
        assert model.kwargs["base_url"] == constants.OPENROUTER_BASE_URL
        # The key is passed straight to the client (not logged, not in headers).
        assert model.kwargs["api_key"] == "test-key-not-real"
        assert "HTTP-Referer" in model.kwargs["default_headers"]

    def test_temperature_override(self) -> None:
        model = build_chat_model(
            _config(), temperature=0.9, chat_openai_cls=_FakeChatOpenAI
        )
        assert model.kwargs["temperature"] == 0.9

    def test_builds_real_langchain_model_without_network(self) -> None:
        # Constructing ChatOpenAI does not call the API; this proves the real
        # integration wires up. Skipped only if langchain-openai is absent.
        pytest.importorskip("langchain_openai")
        from langchain_openai import ChatOpenAI

        model = build_chat_model(_config())
        assert isinstance(model, ChatOpenAI)
