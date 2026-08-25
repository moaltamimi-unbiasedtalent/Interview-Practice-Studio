"""Shared model-responder abstraction for the RAG chain and query translation.

Both the chain and the translator need to call a chat model in a uniform way and
must be testable without the network. They depend on the small ``Responder``
callable and the :class:`ModelReply` value type defined here; the default
responder is backed by the LangChain OpenRouter chat model.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from src.copilot.config import CopilotConfig
from src.copilot.models import UsageRecord

__all__ = ["ModelReply", "Responder", "build_openrouter_responder", "usage_from_lc"]


@dataclass
class ModelReply:
    """A uniform model reply (content + optional token usage)."""

    content: str
    usage: UsageRecord | None = None


#: A responder turns assembled messages into a :class:`ModelReply`.
Responder = Callable[[list[dict]], ModelReply]


def usage_from_lc(message: Any, model: str) -> UsageRecord | None:
    """Extract token usage from a LangChain AIMessage, if present."""
    usage = getattr(message, "usage_metadata", None)
    if isinstance(usage, dict) and usage:
        return UsageRecord(
            model=model,
            prompt_tokens=int(usage.get("input_tokens", 0) or 0),
            completion_tokens=int(usage.get("output_tokens", 0) or 0),
            total_tokens=int(usage.get("total_tokens", 0) or 0),
        )
    return None


def build_openrouter_responder(
    config: CopilotConfig,
    *,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> Responder:
    """Build a responder backed by the LangChain OpenRouter chat model.

    Raises :class:`RagChainError` when no model can be built (missing key).
    """
    from src.copilot.llm.openrouter import CopilotConfigError, build_chat_model
    from src.copilot.rag.chain import RagChainError

    try:
        chat_model = build_chat_model(
            config, model=model, temperature=temperature, max_tokens=max_tokens
        )
    except CopilotConfigError as exc:
        raise RagChainError(str(exc)) from exc

    resolved_model = model or config.default_model
    role_map = {"system": "system", "user": "human", "assistant": "ai"}

    def respond(messages: list[dict]) -> ModelReply:
        lc_messages = [(role_map.get(m["role"], "human"), m["content"]) for m in messages]
        result = chat_model.invoke(lc_messages)
        content = getattr(result, "content", "") or ""
        return ModelReply(content=content, usage=usage_from_lc(result, resolved_model))

    return respond
