"""Tests: Production E2E Validation (Sprint 5.3).

Tests for the E2E validation module: models, scenarios,
executor, runner, and reporter.
"""
from __future__ import annotations

import os
import sys
import pytest
import asyncio

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Data Models (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EModels:
    """Tests for E2E validation data models."""

    def test_scenario_step_creates(self):
        from src.portal.e2e.models import ScenarioStep, StepType
        step = ScenarioStep(
            type=StepType.LOGIN,
            name="Login",
            description="Log into the portal",
            action="login",
            params={"username": "test"},
        )
        assert step.name == "Login"
        assert step.action == "login"
        assert step.status.value == "pending"
        assert step.timeout == 30

    def test_scenario_step_roundtrip(self):
        from src.portal.e2e.models import ScenarioStep, StepType
        step = ScenarioStep(
            type=StepType.NAVIGATE,
            name="Navigate",
            action="navigate",
        )
        d = step.to_dict()
        assert d["type"] == "navigate"
        assert d["name"] == "Navigate"
        assert d["status"] == "pending"

    def test_e2e_scenario_creates(self):
        from src.portal.e2e.models import E2EScenario, ScenarioType
        scenario = E2EScenario(
            type=ScenarioType.HAPPY_PATH,
            name="Test Scenario",
            portal_id="great_eastern",
        )
        assert scenario.name == "Test Scenario"
        assert scenario.portal_id == "great_eastern"
        assert scenario.total_steps == 0
        assert scenario.status.value == "skipped"

    def test_e2e_scenario_with_steps(self):
        from src.portal.e2e.models import E2EScenario, ScenarioStep, StepType, ScenarioType
        scenario = E2EScenario(
            type=ScenarioType.HAPPY_PATH,
            name="Test",
            portal_id="ge",
        )
        scenario.add_step(ScenarioStep(type=StepType.LOGIN, name="Login", action="login"))
        scenario.add_step(ScenarioStep(type=StepType.LOGOUT, name="Logout", action="logout"))
        assert scenario.total_steps == 2
        assert scenario.passed_steps == 0

    def test_e2e_scenario_step_counting(self):
        from src.portal.e2e.models import E2EScenario, ScenarioStep, StepType, StepStatus, ScenarioType
        scenario = E2EScenario(type=ScenarioType.HAPPY_PATH, name="Test", portal_id="ge")
        s1 = ScenarioStep(type=StepType.LOGIN, name="Login", action="login")
        s1.status = StepStatus.PASSED
        s2 = ScenarioStep(type=StepType.LOGOUT, name="Logout", action="logout")
        s2.status = StepStatus.FAILED
        scenario.add_step(s1)
        scenario.add_step(s2)
        assert scenario.passed_steps == 1
        assert scenario.failed_steps == 1

    def test_e2e_report_creates(self):
        from src.portal.e2e.models import E2EReport
        report = E2EReport(portal_id="great_eastern")
        assert report.portal_id == "great_eastern"
        assert report.total_scenarios == 0
        assert report.success_rate == 100.0

    def test_e2e_report_with_scenarios(self):
        from src.portal.e2e.models import (
            E2EReport, E2EScenario, E2EStatus, ScenarioType
        )
        report = E2EReport(portal_id="test")
        s1 = E2EScenario(type=ScenarioType.HAPPY_PATH, name="Pass", portal_id="test",
                          status=E2EStatus.PASSED)
        s2 = E2EScenario(type=ScenarioType.SESSION_TIMEOUT, name="Fail", portal_id="test",
                          status=E2EStatus.FAILED)
        report.scenarios.extend([s1, s2])
        assert report.total_scenarios == 2
        assert report.passed_count == 1
        assert report.failed_count == 1
        assert report.success_rate == 50.0

    def test_e2e_report_roundtrip(self):
        from src.portal.e2e.models import E2EReport, E2EScenario, E2EStatus, ScenarioType
        report = E2EReport(portal_id="ge")
        report.scenarios.append(
            E2EScenario(type=ScenarioType.HAPPY_PATH, name="Test", portal_id="ge",
                         status=E2EStatus.PASSED)
        )
        d = report.to_dict()
        assert d["portal_id"] == "ge"
        assert d["total_scenarios"] == 1
        assert d["passed_count"] == 1


# ══════════════════════════════════════════════════════════════════
# 2. Predefined Scenarios (7 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EScenarios:
    """Tests for predefined E2E scenarios."""

    def test_happy_path_scenario(self):
        from src.portal.e2e.scenarios import happy_path_scenario
        scenario = happy_path_scenario()
        assert scenario.type.value == "happy_path"
        assert scenario.total_steps >= 4
        assert "smoke" in scenario.tags
        assert "core" in scenario.tags

    def test_session_timeout_scenario(self):
        from src.portal.e2e.scenarios import session_timeout_scenario
        scenario = session_timeout_scenario()
        assert scenario.type.value == "session_timeout"
        assert "recovery" in scenario.tags

    def test_browser_crash_scenario(self):
        from src.portal.e2e.scenarios import browser_crash_scenario
        scenario = browser_crash_scenario()
        assert scenario.type.value == "browser_crash"

    def test_network_failure_scenario(self):
        from src.portal.e2e.scenarios import network_failure_scenario
        scenario = network_failure_scenario()
        assert scenario.type.value == "network_failure"

    def test_resume_checkpoint_scenario(self):
        from src.portal.e2e.scenarios import resume_checkpoint_scenario
        scenario = resume_checkpoint_scenario()
        assert scenario.type.value == "resume_checkpoint"

    def test_portal_drift_scenario(self):
        from src.portal.e2e.scenarios import portal_drift_scenario
        scenario = portal_drift_scenario()
        assert scenario.type.value == "portal_drift"

    def test_get_scenario_by_name(self):
        from src.portal.e2e.scenarios import get_scenario, list_scenarios
        scenario = get_scenario("happy_path")
        assert scenario.name == "Happy Path — Full Workflow"
        with pytest.raises(ValueError, match="Unknown scenario"):
            get_scenario("nonexistent")
        available = list_scenarios()
        assert len(available) >= 7
        names = [s["name"] for s in available]
        assert "happy_path" in names or any("happy" in s["name"] for s in available)


# ══════════════════════════════════════════════════════════════════
# 3. Scenario Executor (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestScenarioExecutor:
    """Tests for ScenarioExecutor."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a simple mock adapter for testing."""
        from unittest.mock import MagicMock, AsyncMock
        adapter = MagicMock()
        adapter.login = AsyncMock(return_value=True)
        adapter.logout = AsyncMock(return_value=None)
        adapter.navigate = AsyncMock(return_value=True)
        adapter.recover_session = AsyncMock(return_value=True)
        adapter.check_health = AsyncMock(return_value={"healthy": True})
        adapter.connect = AsyncMock(return_value=None)
        adapter.disconnect = AsyncMock(return_value=None)
        adapter.execute_action = AsyncMock(return_value={"status": "ok"})
        adapter._logged_in = False
        return adapter

    @pytest.mark.asyncio
    async def test_executor_runs_scenario(self, mock_adapter):
        from src.portal.e2e.models import E2EScenario, ScenarioStep, StepType, ScenarioType
        from src.portal.e2e.executor import ScenarioExecutor
        scenario = E2EScenario(type=ScenarioType.HAPPY_PATH, name="Test", portal_id="ge")
        scenario.add_step(ScenarioStep(type=StepType.LOGIN, name="Login", action="login",
                                       params={"username": "u", "password": "p"}))
        scenario.add_step(ScenarioStep(type=StepType.LOGOUT, name="Logout", action="logout"))
        executor = ScenarioExecutor(mock_adapter)
        result = await executor.execute(scenario)
        assert result.status.value == "passed"
        assert result.passed_steps == 2

    @pytest.mark.asyncio
    async def test_executor_handles_step_failure(self, mock_adapter):
        from src.portal.e2e.models import E2EScenario, ScenarioStep, StepType, ScenarioType, StepStatus
        from src.portal.e2e.executor import ScenarioExecutor
        mock_adapter.login = __import__("unittest").mock.AsyncMock(side_effect=Exception("Login failed"))
        scenario = E2EScenario(type=ScenarioType.HAPPY_PATH, name="Test", portal_id="ge")
        scenario.add_step(ScenarioStep(type=StepType.LOGIN, name="Login", action="login",
                                       params={"username": "u", "password": "p"}))
        executor = ScenarioExecutor(mock_adapter)
        result = await executor.execute(scenario)
        assert result.status.value == "failed"
        assert result.steps[0].status == StepStatus.FAILED
        assert "Login failed" in result.steps[0].error

    @pytest.mark.asyncio
    async def test_executor_handles_timeout(self, mock_adapter):
        from src.portal.e2e.models import E2EScenario, ScenarioStep, StepType, ScenarioType, StepStatus
        from src.portal.e2e.executor import ScenarioExecutor
        mock_adapter.login = __import__("unittest").mock.AsyncMock(side_effect=asyncio.TimeoutError())
        scenario = E2EScenario(type=ScenarioType.HAPPY_PATH, name="Test", portal_id="ge")
        scenario.add_step(ScenarioStep(type=StepType.LOGIN, name="Login", action="login",
                                       params={"username": "u", "password": "p"},
                                       timeout=2))
        executor = ScenarioExecutor(mock_adapter)
        result = await executor.execute(scenario)
        assert result.status.value == "failed"

    @pytest.mark.asyncio
    async def test_executor_handles_session_expired(self, mock_adapter):
        from src.portal.e2e.models import E2EScenario, ScenarioStep, StepType, ScenarioType, StepStatus
        from src.portal.e2e.executor import ScenarioExecutor
        scenario = E2EScenario(type=ScenarioType.SESSION_TIMEOUT, name="Timeout", portal_id="ge")
        scenario.add_step(ScenarioStep(type=StepType.LOGIN, name="Login", action="login",
                                       params={"username": "u", "password": "p"}))
        scenario.add_step(ScenarioStep(type=StepType.CUSTOM, name="Clear", action="logout",
                                       inject_error="session_expired"))
        scenario.add_step(ScenarioStep(type=StepType.RECOVER, name="Recover", action="recover_session"))
        executor = ScenarioExecutor(mock_adapter)
        result = await executor.execute(scenario)
        assert result.status.value == "passed"


# ══════════════════════════════════════════════════════════════════
# 4. E2E Runner (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2ERunner:
    """Tests for E2ETestRunner."""

    @pytest.mark.asyncio
    async def test_runner_creates(self):
        from src.portal.e2e.runner import E2ETestRunner
        from src.portal.e2e.reporter import E2EReporter
        runner = E2ETestRunner(portal_id="great_eastern")
        assert runner._portal_id == "great_eastern"
        assert isinstance(runner.reporter, E2EReporter)

    @pytest.mark.asyncio
    async def test_runner_run_scenario_no_adapter(self):
        from src.portal.e2e.runner import E2ETestRunner
        runner = E2ETestRunner(portal_id="great_eastern")
        # Runner auto-loads adapter from registry — should work
        # Try with a nonexistent portal to trigger the error
        runner2 = E2ETestRunner(portal_id="nonexistent_portal")
        with pytest.raises(ValueError, match="No adapter"):
            await runner2.run_all(scenario_names=["happy_path"])

    @pytest.mark.asyncio
    async def test_runner_run_scenario_with_adapter(self):
        from unittest.mock import MagicMock, AsyncMock
        from src.portal.e2e.runner import E2ETestRunner
        from src.portals.base import PortalAdapter

        adapter = MagicMock(spec=PortalAdapter)
        adapter.login = AsyncMock(return_value=True)
        adapter.logout = AsyncMock(return_value=None)
        adapter.navigate = AsyncMock(return_value=True)
        adapter.recover_session = AsyncMock(return_value=True)
        adapter.check_health = AsyncMock(return_value={"healthy": True})
        adapter.connect = AsyncMock(return_value=None)
        adapter.disconnect = AsyncMock(return_value=None)
        adapter.execute_action = AsyncMock(return_value={"status": "ok"})
        adapter._logged_in = False
        adapter.adapter_name = "great_eastern"

        runner = E2ETestRunner(adapter=adapter, portal_id="great_eastern")
        report = await runner.run_all(scenario_names=["happy_path", "session_timeout"])
        assert report.total_scenarios == 2
        assert report.portal_id == "great_eastern"


# ══════════════════════════════════════════════════════════════════
# 5. E2E Reporter (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestE2EReporter:
    """Tests for E2EReporter output formatting."""

    def test_generate_report_includes_portal(self):
        from src.portal.e2e.models import E2EReport
        from src.portal.e2e.reporter import E2EReporter
        report = E2EReport(portal_id="great_eastern")
        reporter = E2EReporter()
        output = reporter.generate_report(report)
        assert "great_eastern" in output
        assert "E2E VALIDATION" in output
        assert "Success Rate" in output

    def test_summary_text(self):
        from src.portal.e2e.models import E2EReport, E2EScenario, E2EStatus, ScenarioType
        from src.portal.e2e.reporter import E2EReporter
        report = E2EReport(portal_id="test")
        report.scenarios.append(
            E2EScenario(type=ScenarioType.HAPPY_PATH, name="Happy", portal_id="test",
                         status=E2EStatus.PASSED)
        )
        reporter = E2EReporter()
        summary = reporter.summary_text(report)
        assert "1/1" in summary
        assert "100%" in summary
