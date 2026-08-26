"""Integration surface between Career Intelligence and Interview Practice.

This is the ONLY place the two modules meet. Data crosses as plain Pydantic
(`PreparationContext`) — never Chroma objects, LangChain documents, retrievers or
career tool internals. Career produces the context; Interview consumes it.
"""

from src.integration.models import PreparationContext, SourceReference

__all__ = ["PreparationContext", "SourceReference"]
