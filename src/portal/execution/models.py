"""Portal Execution Engine — Data Models.

Defines the core data structures for the Portal Execution Engine:
- ExecutionPlan: A complete business task (e.g. "create_quote")
- ExecutionStep: A single executable unit within a plan
- ExecutionContext: Runtime state / execution memory
- ExecutionResult: Structured business result (not browser-level)
- Checkpoint: Snapshot for failure recovery
- RetryPolicy: Retry configuration per step
- StepStatus: Lifecycle state machine
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class StepStatus(Enum):
    """Lifecycle state machine for an ExecutionStep."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


@dataclass
class RetryPolicy:
    """Configuration for step retry behaviour."""

    max_retries: int = 3
    delay_seconds: float = 2.0
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 60.0
    retryable_exceptions: List[str] = field(default_factory=lambda: [
        "TimeoutError",
        "ConnectionError",
        "NavigationError",
        "ElementNotFoundError",
    ])

    @classmethod
    def no_retry(cls) -> "RetryPolicy":
        return cls(max_retries=0)

    @classmethod
    def fast(cls) -> "RetryPolicy":
        """Quick retry for transient failures."""
        return cls(max_retries=2, delay_seconds=0.5, backoff_multiplier=1.0)

    @classmethod
    def aggressive(cls) -> "RetryPolicy":
        """Heavy retry for flaky portals."""
        return cls(max_retries=5, delay_seconds=1.0, backoff_multiplier=2.0)


@dataclass
class ExecutionStep:
    """A single executable unit within an ExecutionPlan.

    A step represents one high-level action (e.g. "login", "create_quote"),
    not a low-level browser operation. The actual implementation is resolved
    through ExecutorRegistry at runtime.

    Lifecycle:
        PENDING → RUNNING → SUCCESS
                          → FAILED → ROLLED_BACK (if rollback defined)
    """

    id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")
    name: str = ""
    action: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy)
    checkpoint_enabled: bool = True
    rollback_action: Optional[str] = None
    rollback_parameters: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    timeout_seconds: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime fields (set during execution)
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0


@dataclass
class ExecutionPlan:
    """Represents a complete business task.

    A plan contains an ordered list of ExecutionSteps that together
    accomplish a business goal (e.g. "create_quote", "renew_policy").

    The plan is built by PlanBuilder from an incoming request and
    executed step-by-step by ExecutionEngine.
    """

    id: str = field(default_factory=lambda: f"plan_{uuid.uuid4().hex[:12]}")
    name: str = ""
    portal: str = ""
    steps: List[ExecutionStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Runtime state
    current_step_index: int = 0
    is_completed: bool = False
    is_failed: bool = False
    is_paused: bool = False

    def next_step(self) -> Optional[ExecutionStep]:
        """Get the next pending step, respecting dependency ordering."""
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                # Check dependencies
                if all(
                    self._get_step(dep).status == StepStatus.SUCCESS
                    for dep in step.depends_on
                    if self._get_step(dep)
                ):
                    return step
        return None

    def _get_step(self, step_id: str) -> Optional[ExecutionStep]:
        for step in self.steps:
            if step.id == step_id or step.name == step_id:
                return step
        return None

    @property
    def progress(self) -> float:
        """Return progress as 0.0–1.0."""
        if not self.steps:
            return 0.0
        completed = sum(
            1 for s in self.steps if s.status in (
                StepStatus.SUCCESS, StepStatus.SKIPPED, StepStatus.ROLLED_BACK
            )
        )
        return completed / len(self.steps)

    @property
    def summary(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "portal": self.portal,
            "progress": self.progress,
            "is_completed": self.is_completed,
            "is_failed": self.is_failed,
            "is_paused": self.is_paused,
            "steps": [
                {"id": s.id, "name": s.name, "action": s.action, "status": s.status.value}
                for s in self.steps
            ],
        }


@dataclass
class ExecutionContext:
    """Runtime state for an active execution.

    Acts as execution memory, accumulating variables as steps complete.
    Accessible to all steps for reading/writing intermediate data.
    """

    execution_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    plan_id: str = ""
    portal: str = ""
    session_id: str = ""
    variables: Dict[str, Any] = field(default_factory=dict)
    current_step_id: Optional[str] = None
    started_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Store a variable in the execution context."""
        self.variables[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a variable from the execution context."""
        return self.variables.get(key, default)

    def update(self, data: Dict[str, Any]) -> None:
        """Batch update variables."""
        self.variables.update(data)


@dataclass
class ExecutionResult:
    """Structured business result returned after execution.

    Does NOT contain browser-level information.
    Contains only business-level results.
    """

    success: bool = False
    execution_id: str = ""
    plan_id: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    completed_steps: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "execution_id": self.execution_id,
            "plan_id": self.plan_id,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "completed_steps": self.completed_steps,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


@dataclass
class Checkpoint:
    """Snapshot of execution state for failure recovery.

    Allows a failed execution to resume from the last successful
    checkpoint rather than restarting from the beginning.
    """

    id: str = field(default_factory=lambda: f"ckpt_{uuid.uuid4().hex[:12]}")
    plan_id: str = ""
    step_index: int = 0
    context: Dict[str, Any] = field(default_factory=dict)
    variables: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


# Type alias for executor callables
ExecutorFunc = Any  # Callable[[ExecutionContext, ExecutionStep], Dict[str, Any]]
