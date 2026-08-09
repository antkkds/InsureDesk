"""InsureDesk — Tool Calling Runtime.

Tools are callable units that an LLM Assistant can invoke.
Each tool has:
- name: unique identifier
- description: natural language description for LLM routing
- parameters: JSON Schema defining expected arguments
- execute(): async implementation

Usage:
    from src.tools import ToolRegistry, register_all_tools
    registry = ToolRegistry()
    register_all_tools(registry)
    result = await registry.execute("create_quote", {...})
"""

from src.tools.base import ToolBase
from src.tools.registry import ToolRegistry
from src.tools.models import ToolExecutionResult
from src.tools.exceptions import (
    ToolError,
    ToolNotFoundError,
    ToolExecutionError,
    ToolRegistrationError,
)
from src.tools.defaults import register_all_tools

__all__ = [
    "ToolBase",
    "ToolRegistry",
    "ToolExecutionResult",
    "ToolError",
    "ToolNotFoundError",
    "ToolExecutionError",
    "ToolRegistrationError",
    "register_all_tools",
]
