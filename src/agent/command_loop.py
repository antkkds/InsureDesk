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
from src.agent.e2e_profile import E2EProfile, E2EProfileEnforcer
from src.agent.handlers import CapabilityHandlerRegistry
from src.agent.result_reporter import ResultReporter
from src.agent.trace import ExecutionTracer, execution_tracer

logger = logging.getLogger(__name__)


class AgentCommandLoop:
    """Poll-and-execute loop for UIP-AI agent commands."""

    def __init__(
        self,
        client: AgentClient,
        handlers: CapabilityHandlerRegistry,
        poll_interval_seconds: float = 3.0,
        reporter: Optional[ResultReporter] = None,
        enforcer: Optional[E2EProfileEnforcer] = None,
        tracer: Optional[ExecutionTracer] = None,
    ) -> None:
        self.client = client
        self.handlers = handlers
        self.poll_interval = poll_interval_seconds
        self.reporter = reporter or ResultReporter()
        # Phase 4.6: enforce the real-validation profile on every command
        self.enforcer = enforcer or E2EProfileEnforcer(
            E2EProfile.from_dict(None)
        )
        self.tracer = tracer or execution_tracer
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.executed_count = 0
        self.failed_count = 0
        self.blocked_count = 0

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
        self.tracer.log(execution_id, "agent_received", {"capability": capability})

        # Phase 4.6: enforce the E2E profile BEFORE executing
        try:
            self.enforcer.check(capability, arguments)
        except Exception as e:  # noqa: BLE001 — policy block
            self.blocked_count += 1
            self.failed_count += 1
            payload = self.reporter.failed(
                str(e), error_code=getattr(e, "error_code", "READ_ONLY_BLOCKED")
            )
            self.tracer.log(execution_id, "blocked_by_policy", {"error": str(e)})
            try:
                self.client.report_result(execution_id, payload)
            except Exception as report_e:  # noqa: BLE001
                logger.error(
                    "agent_command_loop.report_failed: execution=%s: %s",
                    execution_id, report_e,
                )
            return

        handler = self.handlers.get(capability)
        if handler is None:
            logger.warning("agent_command_loop.unknown_capability: '%s'", capability)
            payload = self.reporter.failed(
                f"Unknown capability '{capability}'", error_code="UNKNOWN_CAPABILITY"
            )
        else:
            try:
                self.tracer.log(execution_id, "execution_started", {"capability": capability})
                payload = await handler.execute(arguments)
                self.tracer.log(
                    execution_id, "execution_finished",
                    {"status": payload.get("status")},
                )
            except Exception as e:  # noqa: BLE001 — surface as protocol failure
                payload = self.reporter.failed(e)
        try:
            self.client.report_result(execution_id, payload)
            if payload.get("status") == "success":
                self.executed_count += 1
            else:
                self.failed_count += 1
            self.tracer.log(
                execution_id, "result_reported", {"status": payload.get("status")}
            )
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
