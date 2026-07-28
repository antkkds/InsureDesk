"""InsureDesk — Production E2E Validation: Runner.

Orchestrates execution of multiple E2E scenarios
against a portal adapter and aggregates results.
"""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Dict, List, Optional

from src.portal.e2e.models import (
    E2EScenario, E2EReport, E2EStatus, ScenarioType,
)
from src.portal.e2e.executor import ScenarioExecutor
from src.portal.e2e.scenarios import get_scenario, list_scenarios
from src.portal.e2e.reporter import E2EReporter
from src.portals.base import PortalAdapter, get_adapter
from src.portals.base import PortalCredentials

logger = logging.getLogger("insuredesk.e2e.runner")


class E2ETestRunner:
    """Orchestrates E2E validation of a portal adapter.

    Runs multiple scenarios, collects results,
    and generates a comprehensive report.

    Usage:
        runner = E2ETestRunner(adapter)
        report = await runner.run_all()
        print(runner.reporter.summary(report))
    """

    def __init__(self, adapter: Optional[PortalAdapter] = None,
                 portal_id: str = "great_eastern",
                 reporter: Optional[E2EReporter] = None):
        self._adapter = adapter
        self._portal_id = portal_id
        self._reporter = reporter or E2EReporter()

    async def run_all(self, scenario_names: Optional[List[str]] = None) -> E2EReport:
        """Run all (or selected) E2E scenarios.

        Args:
            scenario_names: List of scenario names to run.
                If None, runs all available scenarios.

        Returns:
            E2EReport with results from all scenarios.
        """
        if self._adapter is None:
            self._adapter = get_adapter(self._portal_id)

        if self._adapter is None:
            raise ValueError(f"No adapter found for portal: {self._portal_id}")

        # Determine which scenarios to run
        if scenario_names is None:
            scenario_names = list(ScenarioType._value2member_map_.keys())

        report = E2EReport(portal_id=self._portal_id)
        start = time.monotonic()

        for name in scenario_names:
            try:
                scenario = get_scenario(name, self._portal_id)
                executor = ScenarioExecutor(self._adapter)
                result = await executor.execute(scenario)
                report.scenarios.append(result)
                logger.info(
                    f"Scenario '{name}': {result.status.value} "
                    f"({result.passed_steps}/{result.total_steps} steps)"
                )
            except ValueError as e:
                logger.warning(f"Skipping unknown scenario '{name}': {e}")
                continue
            except Exception as e:
                logger.error(f"Scenario '{name}' error: {e}")
                failed = E2EScenario(
                    type=ScenarioType.HAPPY_PATH,  # placeholder
                    name=name,
                    portal_id=self._portal_id,
                    status=E2EStatus.ERROR,
                    error=str(e),
                )
                report.scenarios.append(failed)

        report.total_duration = time.monotonic() - start
        return report

    async def run_scenario(self, name: str) -> E2EScenario:
        """Run a single scenario by name."""
        if self._adapter is None:
            self._adapter = get_adapter(self._portal_id)
        scenario = get_scenario(name, self._portal_id)
        executor = ScenarioExecutor(self._adapter)
        return await executor.execute(scenario)

    @property
    def reporter(self) -> E2EReporter:
        return self._reporter
