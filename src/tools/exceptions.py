"""InsureDesk Tools — Tool-level exceptions.

These are distinct from:
- runtime/errors.py (ExtractionError → adapter/data errors)
- runtime/browser_session.py (BrowserError → browser automation errors)

Tool errors are about tool registration and execution lifecycle.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class ToolError(Exception):
    """Base exception for all tool-related errors."""

    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}


class ToolNotFoundError(ToolError):
    """Raised when a tool name is not registered."""

    def __init__(self, tool_name: str, available: Optional[list] = None):
        super().__init__(
            f"Tool '{tool_name}' not found",
            context={
                "tool_name": tool_name,
                "available_tools": available or [],
            },
        )


class ToolExecutionError(ToolError):
    """Raised when a tool fails during execution."""

    def __init__(self, tool_name: str, original_error: str):
        super().__init__(
            f"Tool '{tool_name}' execution failed: {original_error}",
            context={
                "tool_name": tool_name,
                "original_error": original_error,
            },
        )


class ToolRegistrationError(ToolError):
    """Raised when a tool cannot be registered (duplicate name, invalid)."""

    def __init__(self, tool_name: str, reason: str):
        super().__init__(
            f"Cannot register tool '{tool_name}': {reason}",
            context={"tool_name": tool_name, "reason": reason},
        )
