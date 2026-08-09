"""InsureDesk Tools — Tool execution result types.

ToolExecutionResult is the internal tool layer result.
BridgeServer converts it to BridgeResponse (transport layer).

Design:
    ToolExecutionResult (internal)
        |
        v
    BridgeResponse (transport)
    
Conversion happens in bridge/server.py, NOT in tools.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class ToolExecutionResult:
    """Result of a tool execution.

    This is the INTERNAL result type used within the tool layer.
    BridgeServer converts this to the appropriate transport format.

    Attributes:
        success: Whether the tool executed successfully.
        data: Result data (any JSON-serializable value).
        error: Human-readable error message (None if success).
        error_code: Machine-readable error code (None if success).
        error_context: Structured error context for debugging.
    """

    success: bool = True
    data: Any = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    error_context: Dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    @classmethod
    def ok(cls, data: Any = None) -> "ToolExecutionResult":
        """Create a successful result."""
        return cls(success=True, data=data)

    @classmethod
    def fail(
        cls,
        error: str,
        error_code: str = "tool_error",
        error_context: Optional[Dict[str, Any]] = None,
    ) -> "ToolExecutionResult":
        """Create a failed result."""
        return cls(
            success=False,
            error=error,
            error_code=error_code,
            error_context=error_context or {},
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for transport conversion."""
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code,
            "error_context": self.error_context,
        }
