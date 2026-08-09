"""InsureDesk — Production E2E Validation: Scenario Executor.

Executes individual E2E scenario steps against a portal adapter,
with error handling, retries, and timeouts.
"""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Any, Dict, Optional

from src.portal.e2e.models import (
    E2EScenario, ScenarioStep, StepStatus, E2EStatus, StepType,
)
from src.portal.e2e.exceptions import (
    ScenarioExecutionError, StepTimeoutError,
)
from src.portals.base import PortalAdapter, PortalCredentials

logger = logging.getLogger("insuredesk.e2e.executor")


class ScenarioExecutor:
    """Executes a single E2E scenario against a portal adapter.

    Handles step-level execution, retries, timeouts,
    and error injection for failure scenarios.
    """

    def __init__(self, adapter: PortalAdapter):
        self._adapter = adapter

    async def execute(self, scenario: E2EScenario) -> E2EScenario:
        """Execute all steps in a scenario.

        Args:
            scenario: The scenario to execute.

        Returns:
            The same scenario with step statuses populated.
        """
        scenario.status = E2EStatus.RUNNING
        start = time.monotonic()

        for step in scenario.steps:
            step.status = StepStatus.RUNNING
            step_start = time.monotonic()

            try:
                await self._execute_step(step, scenario)
                step.status = StepStatus.PASSED
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)
                logger.error(f"Step '{step.name}' failed: {e}")
                # On failure, continue to next step for full diagnostic
                # (don't abort the entire scenario)

            step.duration = time.monotonic() - step_start

        scenario.total_duration = time.monotonic() - start

        # Determine overall status
        failed = any(s.status in (StepStatus.FAILED, StepStatus.ERROR) for s in scenario.steps)
        if failed:
            scenario.status = E2EStatus.FAILED
        else:
            scenario.status = E2EStatus.PASSED

        return scenario

    async def _execute_step(self, step: ScenarioStep,
                             scenario: E2EScenario) -> Any:
        """Execute a single step with retry logic."""
        last_error = None

        for attempt in range(step.retry_count + 1):
            try:
                result = await asyncio.wait_for(
                    self._run_step_action(step),
                    timeout=step.timeout,
                )
                step.output = result
                return result

            except asyncio.TimeoutError:
                last_error = StepTimeoutError(step.name, step.timeout)
                logger.warning(f"Step '{step.name}' timeout (attempt {attempt + 1})")
                if attempt < step.retry_count:
                    await asyncio.sleep(step.retry_delay)
                continue

            except Exception as e:
                last_error = e
                logger.warning(f"Step '{step.name}' error (attempt {attempt + 1}): {e}")
                if attempt < step.retry_count:
                    await asyncio.sleep(step.retry_delay)
                continue

        raise last_error or ScenarioExecutionError(
            scenario.name, step.name, "All retries exhausted"
        )

    async def _run_step_action(self, step: ScenarioStep) -> Any:
        """Execute the action defined by a step."""
        adapter = self._adapter

        # Handle error injection (for simulating failure scenarios)
        if step.inject_error:
            self._handle_injected_error(step.inject_error)

        # Dispatch to adapter methods
        if step.action == "login":
            return await adapter.login(
                PortalCredentials(
                    username=step.params.get("username", ""),
                    password=step.params.get("password", ""),
                )
            )
        elif step.action == "logout":
            return await adapter.logout()
        elif step.action == "disconnect":
            return await adapter.disconnect()
        elif step.action == "connect":
            return await adapter.connect()
        elif step.action == "navigate":
            return await adapter.navigate(step.params.get("route_name", ""))
        elif step.action == "execute_action":
            return await adapter.execute_action(
                step.params.get("action_type", ""),
                step.params.get("params"),
            )
        elif step.action == "recover_session":
            return await adapter.recover_session()
        elif step.action == "health_check":
            return await adapter.check_health()
        else:
            raise ValueError(f"Unknown step action: {step.action}")

    def _handle_injected_error(self, error_type: str) -> None:
        """Simulate an error for testing failure scenarios.

        Raises an exception that mimics real-world failures.
        """
        if error_type == "session_expired":
            # Force session to appear expired
            self._adapter._logged_in = False
        elif error_type == "browser_crash":
            # Simulate browser crash by clearing engine state
            self._adapter._engine = None
            self._adapter._logged_in = False
        elif error_type == "network_timeout":
            raise asyncio.TimeoutError("Simulated network timeout")
        elif error_type == "save_checkpoint":
            pass  # No-op, checkpoint save is just a marker
