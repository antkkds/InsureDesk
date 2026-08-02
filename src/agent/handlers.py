"""InsureDesk — Capability Handler Registry.

Maps UIP-AI capabilities (insurance.quote.calculate) to local execution
handlers — NEVER hardcode ``if capability == "..."`` chains (future
capabilities would become hardcoded again).

    Agent Command
        ↓
    CapabilityHandlerRegistry
        ↓
    QuoteCapabilityHandler
        ↓
    QuoteExecutor (existing src/quote/)
        ↓
    Portal
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class CapabilityHandler(ABC):
    """Base class for a local capability handler."""

    @property
    @abstractmethod
    def capability(self) -> str:
        """Capability name this handler serves."""

    @abstractmethod
    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Execute the capability with the given arguments.

        Returns the protocol result payload (see result_reporter).
        """


class QuoteCapabilityHandler(CapabilityHandler):
    """Handles insurance.quote.calculate via the existing quote pipeline."""

    @property
    def capability(self) -> str:
        return "insurance.quote.calculate"

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from src.agent.result_reporter import ResultReporter

        reporter = ResultReporter()
        mode = arguments.get("execution_mode", "simulation")
        try:
            registry = ToolRegistry.get_instance()
            # Lazy-register the existing quote tools if not present (thin
            # layer — never replaces the ToolRegistry).
            if not registry.has_tool("create_quote"):
                from src.tools.insurance.quote_tools import register_all_quote_tools

                register_all_quote_tools(registry)
            result = await registry.execute("create_quote", **arguments)
            if not result.success:
                return reporter.failed(
                    result.error or "create_quote failed",
                )
            # Normalize tool output into a protocol result
            data = result.data or {}
            return reporter.success(
                {
                    "quote_number": data.get("quote_number"),
                    "premium": data.get("premium"),
                    "status": data.get("status", "draft"),
                    "proposer_name": data.get("proposer_name"),
                },
                execution_mode=mode,
            )
        except Exception as e:  # noqa: BLE001 — surface as protocol failure
            logger.exception("quote handler failed: %s", e)
            return reporter.failed(e)


class CapabilityHandlerRegistry:
    """Registry of capability → local handler."""

    def __init__(self) -> None:
        self._handlers: Dict[str, CapabilityHandler] = {}

    def register(self, handler: CapabilityHandler) -> None:
        self._handlers[handler.capability] = handler
        logger.info("capability_handler.registered: '%s'", handler.capability)

    def get(self, capability: str) -> Optional[CapabilityHandler]:
        return self._handlers.get(capability)

    def has(self, capability: str) -> bool:
        return capability in self._handlers

    def list(self) -> list[str]:
        return sorted(self._handlers.keys())

    def register_defaults(self) -> None:
        """Register all built-in handlers (idempotent)."""
        self.register(QuoteCapabilityHandler())
