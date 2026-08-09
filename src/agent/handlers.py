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
    """Handles insurance.quote.calculate via the existing quote pipeline.

    Phase 4.5 safety: the capability is declared readonly in the manifest —
    the handler refuses mutating actions (save_draft/submit) with
    READ_ONLY_BLOCKED.
    """

    MUTATING_KEYWORDS = ("submit", "save_draft", "save", "issue", "delete")

    @property
    def capability(self) -> str:
        return "insurance.quote.calculate"

    async def execute(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        from src.agent.result_reporter import ResultReporter

        reporter = ResultReporter()
        mode = arguments.get("execution_mode", "simulation")

        # Phase 4.5 safety gate — readonly policy blocks mutating intents
        if any(
            kw in self.capability.lower() or kw in str(arguments).lower()
            for kw in self.MUTATING_KEYWORDS
        ):
            logger.warning(
                "quote handler blocked by readonly policy: %s", arguments,
            )
            return reporter.blocked(self.capability)

        try:
            registry = ToolRegistry.get_instance()
            # Lazy-register quote tools if not present (thin layer — never
            # replaces the ToolRegistry). Prefer the REAL portal executor
            # (calculate_quote) when available; fall back to the simulation
            # tools (create_quote) otherwise.
            if not registry.has_tool("calculate_quote") and not registry.has_tool("create_quote"):
                try:
                    # Desktop build: real portal executor (CalculateQuoteTool)
                    from src.tools.defaults import register_all_tools

                    register_all_tools(registry)
                except ImportError:
                    pass
                if not registry.has_tool("calculate_quote"):
                    try:
                        # WSL dev build: simulation quote tools
                        from src.tools.insurance.quote_tools import register_all_quote_tools

                        register_all_quote_tools(registry)
                    except ImportError:
                        # Neither tool set present — let execution surface
                        # the tool-not-found error clearly.
                        pass
            tool_name = "calculate_quote" if registry.has_tool("calculate_quote") else "create_quote"
            if mode == "simulation":
                # Simulation mode must NOT touch the real portal executor;
                # always use the mock create_quote pipeline.
                if not registry.has_tool("create_quote"):
                    try:
                        from src.tools.insurance.quote_tools import CreateQuote
                        registry.register(CreateQuote())
                    except ImportError:
                        pass
                tool_name = "create_quote"
            if tool_name == "calculate_quote":
                # Real portal execution needs a browser engine. If the tool
                # registry has no context, lazily create one (Chrome CDP).
                try:
                    from src.browser import create_browser_engine
                    from src.portal.form_engine import FormEngine

                    engine = create_browser_engine()
                    arguments = dict(arguments)
                    arguments.setdefault("_form_engine", FormEngine(engine))
                except Exception:
                    pass
            result = await registry.execute(tool_name, **arguments)
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
