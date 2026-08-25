"""RAG package: prompts, context building, citations and the baseline chain."""

from src.copilot.rag.chain import RagChain, RagChainError
from src.copilot.rag.context import ContextBundle, build_context
from src.copilot.rag.prompts import build_messages, system_prompt

__all__ = [
    "RagChain",
    "RagChainError",
    "ContextBundle",
    "build_context",
    "build_messages",
    "system_prompt",
]
