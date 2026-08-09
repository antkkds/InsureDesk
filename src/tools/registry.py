"""InsureDesk Tools — Tool Registry.

Central registry for all executable tools.
Tools are registered at startup and dispatched by BridgeServer.

Design principles:
    - No hard singleton — pass registry via dependency injection
    - Tools are stateless — all state in execution context
    - Registration happens once at startup
    - Thread-safe for read operations
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.tools.base import ToolBase
from src.tools.models import ToolExecutionResult
from src.tools.exceptions import (
    ToolNotFoundError,
    ToolRegistrationError,
    ToolExecutionError,
)


class ToolRegistry:
    """Registry for discovering and executing tools.

    Usage:
        registry = ToolRegistry()
        registry.register(MyTool())
        result = await registry.execute("my_tool", {"arg": "val"})
    """

    def __init__(self):
        self._tools: Dict[str, ToolBase] = {}

    # ── Singleton (backward compat with legacy callers/tests) ──

    _instance: Optional["ToolRegistry"] = None

    @classmethod
    def get_instance(cls) -> "ToolRegistry":
        """Get or create the singleton registry instance (legacy API)."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton (legacy API, for tests)."""
        cls._instance = None

    # ── Registration ──

    def register(self, tool: ToolBase) -> None:
        """Register a tool.

        Args:
            tool: A ToolBase instance.

        Raises:
            ToolRegistrationError: If a tool with the same name is already
                registered, or if the tool has no name.
        """
        if not tool.name:
            raise ToolRegistrationError(
                type(tool).__name__, "Tool has empty 'name' attribute"
            )
        if tool.name in self._tools:
            raise ToolRegistrationError(
                tool.name, f"Already registered: {type(self._tools[tool.name]).__name__}"
            )
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> bool:
        """Remove a tool by name.

        Args:
            name: Tool name to remove.

        Raises:
            KeyError: If tool not found.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        del self._tools[name]

    def register_all(self, tools: List[ToolBase]) -> None:
        """Register multiple tools at once.

        Args:
            tools: Iterable of ToolBase instances.

        Raises:
            ToolRegistrationError: If any tool has an empty name or a
                duplicate name is already registered.
        """
        for tool in tools:
            self.register(tool)

    # ── Discovery ──

    def list_tools(self) -> List[Dict[str, Any]]:
        """List all registered tools with metadata.

        Returns:
            List of dicts with name and description.
        """
        return [
            {"name": t.name, "description": t.description}
            for t in self._tools.values()
        ]

    def get(self, name: str) -> ToolBase:
        """Get a tool by name.

        Args:
            name: Tool name.

        Returns:
            The ToolBase instance.

        Raises:
            ToolNotFoundError: If the tool is not registered.
        """
        if name not in self._tools:
            available = list(self._tools.keys())
            raise ToolNotFoundError(name, available=available)
        return self._tools[name]

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    # ── Execution ──

    async def execute(
        self,
        name: str,
        arguments: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> ToolExecutionResult:
        """Execute a tool by name.

        Args:
            name: Tool name to execute.
            arguments: Tool-specific arguments (dict).
            context: Optional shared execution context.
            **kwargs: Legacy style — keyword arguments treated as tool args
                (e.g. execute("create_quote", proposer_name="x")).

        Returns:
            ToolExecutionResult with success or error info.

        Raises:
            ToolNotFoundError: If the tool is not registered.
        """
        tool = self.get(name)
        # Legacy style: keyword args passed directly to tool
        if arguments is None and kwargs:
            arguments = kwargs
        arguments = arguments or {}
        try:
            return await tool.execute(arguments, context=context)
        except ToolExecutionError:
            raise
        except Exception as e:
            return ToolExecutionResult.fail(
                error=str(e),
                error_code="tool_execution_error",
                error_context={"tool_name": name, "exception_type": type(e).__name__},
            )

    def count(self) -> int:
        """Number of registered tools (legacy alias for tool_count)."""
        return len(self._tools)

    # ── Stats ──

    @property
    def tool_count(self) -> int:
        """Number of registered tools."""
        return len(self._tools)

    def stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "tool_count": self.tool_count,
            "tools": self.list_tools(),
        }
