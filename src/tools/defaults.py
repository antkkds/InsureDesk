"""InsureDesk Tools — Default tool registration.

Central place to register all built-in tools.
Called once at application startup.

This module exists to prevent circular imports:
    registry.py should NOT import business tools directly.
"""

from __future__ import annotations

from src.tools.registry import ToolRegistry
from src.tools.quote import CalculateQuoteTool
from src.tools.capture import CaptureModeTool


def register_all_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools.

    Call once at application startup:
        registry = ToolRegistry()
        register_all_tools(registry)

    Phase 3: CalculateQuoteTool registered.
    Phase 4C: CaptureModeTool registered.
    Future: PolicyTool, ClaimTool, DocumentTool, etc.
    """
    registry.register(CalculateQuoteTool())
    registry.register(CaptureModeTool())
