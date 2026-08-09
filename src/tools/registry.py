"""InsureDesk — Tool Registry.

Singleton registry for all callable tools.
Supports registration, lookup, listing, and execution.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Type

from src.tools.base import ToolBase, ToolResult


class ToolRegistry:
    """Central registry for all tools.

    Usage:
        registry = ToolRegistry.get_instance()
        registry.register(MyTool())
        tools = registry.list_tools()
        result = await registry.execute("my_tool", {...})
    """

    _instance: Optional["ToolRegistry"] = None

    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}

    # ── Singleton ──────────────────────────────────────────────

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Get or create the singleton registry instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (for testing)."""
        cls._instance = None

    # ── Registration ──────────────────────────────────────────

    def register(self, tool: ToolBase) -> None:
        """Register a tool by its name.

        Args:
            tool: ToolBase instance.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(f"Tool '{tool.name}' is already registered")
        self._tools[tool.name] = tool

    def register_all(self, tools: List[ToolBase]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry.

        Args:
            name: Tool name to remove.

        Raises:
            KeyError: If tool not found.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        del self._tools[name]

    # ── Lookup ───────────────────────────────────────────────

    def get_tool(self, name: str) -> Optional[ToolBase]:
        """Get a tool by name.

        Args:
            name: Tool name.

        Returns:
            ToolBase instance or None if not found.
        """
        return self._tools.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    # ── Listing ──────────────────────────────────────────────

    def list_tools(self) -> List[dict]:
        """List all registered tools as definitions.

        Returns:
            List of tool definitions usable as LLM function schemas.
        """
        return [tool.to_definition() for tool in self._tools.values()]

    def list_tools_simple(self) -> List[dict]:
        """List tools with name, description, and parameter count."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "parameter_count": len(t.parameters.get("properties", {})),
            }
            for t in self._tools.values()
        ]

    def count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)

    # ── Execution ────────────────────────────────────────────

    async def execute(self, name: str, **kwargs) -> ToolResult:
        """Execute a tool by name with given parameters.

        Args:
            name: Tool name to execute.
            **kwargs: Parameters passed to the tool's execute().

        Returns:
            ToolResult with execution result.

        Raises:
            KeyError: If tool not found.
        """
        tool = self.get_tool(name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' not found. Available: {', '.join(self._tools.keys())}",
            )

        start = time.perf_counter()
        try:
            result = await tool.execute(**kwargs)
            elapsed = (time.perf_counter() - start) * 1000
            result.duration_ms = elapsed
            return result
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                duration_ms=elapsed,
            )
