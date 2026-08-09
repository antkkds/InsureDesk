"""InsureDesk — Tool Base Class.

All tools inherit from ToolBase and implement:
- name: str (unique identifier)
- description: str (for LLM routing)
- parameters: dict (JSON Schema)
- execute(**kwargs) -> ToolResult
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Optional
from datetime import datetime


@dataclass
class ToolResult:
    """Standard result from a tool execution."""
    success: bool
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "timestamp": self.timestamp,
        }


class ToolBase(ABC):
    """Base class for all callable tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name (snake_case)."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Natural language description for LLM routing."""
        ...

    @property
    def parameters(self) -> dict:
        """JSON Schema for expected arguments.

        Override in subclass to define parameter schema.
        Default: empty object (no parameters).
        """
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters.

        Args:
            **kwargs: Parameters matching the JSON schema.

        Returns:
            ToolResult with success/data/error.
        """
        ...

    def to_definition(self) -> dict:
        """Return tool definition for LLM function calling."""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
