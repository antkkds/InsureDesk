"""InsureDesk — Production E2E Validation: Data Models.

Models for defining, executing, and reporting
end-to-end validation scenarios against real portals.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ScenarioType(Enum):
    """Types of E2E validation scenarios."""
    HAPPY_PATH = "happy_path"
    SESSION_TIMEOUT = "session_timeout"
    BROWSER_CRASH = "browser_crash"
    NETWORK_FAILURE = "network_failure"
    RESUME_CHECKPOINT = "resume_checkpoint"
    PORTAL_DRIFT = "portal_drift"
    AUTH_FAILURE = "auth_failure"
    RECOVERY = "recovery"


class StepType(Enum):
    """Types of steps within a scenario."""
    LOGIN = "login"
    NAVIGATE = "navigate"
    FILL = "fill"
    CLICK = "click"
    EXTRACT = "extract"
    VALIDATE = "validate"
    WAIT = "wait"
    LOGOUT = "logout"
    RECOVER = "recover"
    ASSERT = "assert"
    CUSTOM = "custom"


class StepStatus(Enum):
    """Execution status of a scenario step."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


class E2EStatus(Enum):
    """Overall status of an E2E test run."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class ScenarioStep:
    """A single step within an E2E scenario.

    Each step represents one action: login, navigate, fill form,
    extract data, validate output, etc.
    """
    id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:6]}")
    type: StepType = StepType.CUSTOM
    name: str = ""
    description: str = ""
    action: str = ""  # portal adapter action name
    params: Dict[str, Any] = field(default_factory=dict)
    expected: Optional[Dict[str, Any]] = None  # Expected result for validation
    timeout: int = 30  # Max seconds for this step
    retry_count: int = 0  # Max retries on failure
    retry_delay: float = 1.0  # Seconds between retries
    inject_error: Optional[str] = None  # For error scenarios
    status: StepStatus = StepStatus.PENDING
    error: Optional[str] = None
    duration: float = 0.0
    output: Optional[Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "action": self.action,
            "params": self.params,
            "expected": self.expected,
            "timeout": self.timeout,
            "retry_count": self.retry_count,
            "status": self.status.value,
            "error": self.error,
            "duration": self.duration,
        }


@dataclass
class E2EScenario:
    """A complete E2E validation scenario.

    Defines a sequence of steps that test a specific
    portal behavior or failure mode.
    """
    id: str = field(default_factory=lambda: f"e2e_{uuid.uuid4().hex[:6]}")
    type: ScenarioType = ScenarioType.HAPPY_PATH
    name: str = ""
    description: str = ""
    portal_id: str = ""
    steps: List[ScenarioStep] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    timeout: int = 300  # Max total seconds
    requires_browser: bool = True
    status: E2EStatus = E2EStatus.SKIPPED
    error: Optional[str] = None
    total_duration: float = 0.0

    @property
    def passed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.PASSED)

    @property
    def failed_steps(self) -> int:
        return sum(1 for s in self.steps if s.status in (StepStatus.FAILED, StepStatus.ERROR))

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    def add_step(self, step: ScenarioStep) -> None:
        self.steps.append(step)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "name": self.name,
            "description": self.description,
            "portal_id": self.portal_id,
            "steps": [s.to_dict() for s in self.steps],
            "tags": self.tags,
            "status": self.status.value,
            "error": self.error,
            "total_duration": self.total_duration,
            "passed_steps": self.passed_steps,
            "failed_steps": self.failed_steps,
            "total_steps": self.total_steps,
        }


@dataclass
class E2EReport:
    """Complete E2E test run report."""
    id: str = field(default_factory=lambda: f"rpt_{uuid.uuid4().hex[:6]}")
    timestamp: datetime = field(default_factory=datetime.now)
    portal_id: str = ""
    scenarios: List[E2EScenario] = field(default_factory=list)
    total_duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_scenarios(self) -> int:
        return len(self.scenarios)

    @property
    def passed_count(self) -> int:
        return sum(1 for s in self.scenarios if s.status == E2EStatus.PASSED)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.scenarios if s.status == E2EStatus.FAILED)

    @property
    def total_steps(self) -> int:
        return sum(s.total_steps for s in self.scenarios)

    @property
    def passed_steps(self) -> int:
        return sum(s.passed_steps for s in self.scenarios)

    @property
    def failed_steps(self) -> int:
        return sum(s.failed_steps for s in self.scenarios)

    @property
    def success_rate(self) -> float:
        if not self.total_scenarios:
            return 100.0
        return (self.passed_count / self.total_scenarios) * 100

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "portal_id": self.portal_id,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "total_duration": self.total_duration,
            "total_scenarios": self.total_scenarios,
            "passed_count": self.passed_count,
            "failed_count": self.failed_count,
            "success_rate": self.success_rate,
        }
