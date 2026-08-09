"""InsureDesk — Production E2E Validation: Exceptions."""
from __future__ import annotations


class E2EError(Exception):
    """Base exception for E2E validation errors."""
    pass


class ScenarioExecutionError(E2EError):
    """Error during scenario execution."""
    def __init__(self, scenario_name: str, step_name: str, reason: str):
        super().__init__(f"Scenario '{scenario_name}' failed at step '{step_name}': {reason}")
        self.scenario_name = scenario_name
        self.step_name = step_name


class StepTimeoutError(E2EError):
    """A scenario step exceeded its timeout."""
    def __init__(self, step_name: str, timeout: int):
        super().__init__(f"Step '{step_name}' timed out after {timeout}s")
        self.step_name = step_name
        self.timeout = timeout


class ValidationError(E2EError):
    """Scenario result validation failed."""
    def __init__(self, scenario_name: str, detail: str):
        super().__init__(f"Validation failed for '{scenario_name}': {detail}")
        self.scenario_name = scenario_name


class BrowserNotAvailableError(E2EError):
    """Browser engine is not available for E2E test."""
    pass
