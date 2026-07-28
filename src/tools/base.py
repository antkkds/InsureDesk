"""InsureDesk Tools — ToolBase abstract interface.

Every tool in InsureDesk implements this interface.
Tools are registered in ToolRegistry and executed via BridgeServer.

Architecture:
    UIP-AI Cloud → BridgeServer → ToolRegistry → ToolBase.execute()
                                                        |
                                                        v
                                              ToolExecutionResult
                                                        |
                                                        v
                                              BridgeResponse (conversion)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.tools.models import ToolExecutionResult


class ToolBase(ABC):
    """Abstract base class for all InsureDesk tools.

    Each tool is a self-contained executable action.
    Tools are stateless — all state lives in the context.

    Attributes:
        name: Unique tool identifier (e.g. 'calculate_quote')
        description: Human-readable description for discovery
    """

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(
        self,
        arguments: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute the tool with given arguments.

        Args:
            arguments: Tool-specific parameters from the caller.
            context: Optional shared context (session, credentials, browser).

        Returns:
            ToolExecutionResult with success/data or error/error_code.
        """
        ...
