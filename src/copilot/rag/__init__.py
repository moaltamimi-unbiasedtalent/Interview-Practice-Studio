"""RAG package: prompts, context, citations, translation and the chain."""

from src.copilot.rag.chain import RagChain, RagChainError
from src.copilot.rag.context import ContextBundle, build_context
from src.copilot.rag.prompts import build_messages, system_prompt
from src.copilot.rag.responder import ModelReply, Responder
from src.copilot.rag.translation import QueryTranslator, heuristic_translation

__all__ = [
    "RagChain",
    "RagChainError",
    "ContextBundle",
    "build_context",
    "build_messages",
    "system_prompt",
    "ModelReply",
    "Responder",
    "QueryTranslator",
    "heuristic_translation",
]
