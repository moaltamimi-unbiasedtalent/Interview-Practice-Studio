"""Tool error types."""

from __future__ import annotations

__all__ = ["ToolError", "ToolDependencyError"]


class ToolError(Exception):
    """Base class for tool execution errors (safe messages only)."""


class ToolDependencyError(ToolError):
    """Raised when a tool needs a model/config that is not available."""
