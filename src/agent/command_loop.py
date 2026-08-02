"""InsureDesk — Agent Command Loop.

Core Phase 4.3 loop:
    while running:
        commands = client.poll_commands()
        for command in commands:
            handler = registry.get(command.capability)
            result = await handler.execute(command.arguments)
            client.report_result(command.execution_id, result)

Runs in a background thread with its own asyncio loop so it does NOT
block the desktop app's main thread.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Optional

from src.agent.client import AgentClient
from src.agent.handlers import CapabilityHandlerRegistry
from src.agent.result_reporter import ResultReporter

logger = logging.getLogger(__name__)


class AgentCommandLoop:
    """Poll-and-execute loop for UIP-AI agent commands."""

    def __init__(
        self,
        client: AgentClient,
        handlers: CapabilityHandlerRegistry,
        poll_interval_seconds: float = 3.0,
        reporter: Optional[ResultReporter] = None,
    ) -> None:
        self.client = client
        self.handlers = handlers
        self.poll_interval = poll_interval_seconds
        self.reporter = reporter or ResultReporter()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.executed_count = 0
        self.failed_count = 0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_loop, name="agent-command-loop", daemon=True
        )
        self._thread.start()
        logger.info("agent_command_loop.started (poll every %ss)", self.poll_interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        logger.info(
            "agent_command_loop.stopped (executed=%d failed=%d)",
            self.executed_count, self.failed_count,
        )

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._poll_forever())
        except Exception as e:  # noqa: BLE001 — loop must not crash the app
            logger.exception("agent_command_loop crashed: %s", e)
        finally:
            loop.close()

    async def _poll_forever(self) -> None:
        while not self._stop.is_set():
            try:
                commands = self.client.poll_commands()
                for command in commands:
                    await self._execute(command.execution_id, command.capability, command.arguments)
            except Exception as e:  # noqa: BLE001 — transient network issues
                logger.warning("agent_command_loop.poll_failed: %s", e)
            await asyncio.sleep(self.poll_interval)

    async def _execute(self, execution_id: str, capability: str, arguments: dict) -> None:
        handler = self.handlers.get(capability)
        if handler is None:
            logger.warning("agent_command_loop.unknown_capability: '%s'", capability)
            payload = self.reporter.failed(
                f"Unknown capability '{capability}'", error_code="UNKNOWN_CAPABILITY"
            )
        else:
            try:
                payload = await handler.execute(arguments)
            except Exception as e:  # noqa: BLE001 — surface as protocol failure
                payload = self.reporter.failed(e)
        try:
            self.client.report_result(execution_id, payload)
            if payload.get("status") == "success":
                self.executed_count += 1
            else:
                self.failed_count += 1
            logger.info(
                "agent_command_loop.executed: execution=%s capability=%s status=%s",
                execution_id, capability, payload.get("status"),
            )
        except Exception as e:  # noqa: BLE001 — result delivery failure
            self.failed_count += 1
            logger.error(
                "agent_command_loop.report_failed: execution=%s: %s",
                execution_id, e,
            )
