"""Portal Execution Engine — Exceptions."""

from __future__ import annotations


class ExecutionError(Exception):
    """Base exception for execution engine errors."""


class StepExecutionError(ExecutionError):
    """Raised when a step fails during execution."""


class CheckpointNotFoundError(ExecutionError):
    """Raised when a requested checkpoint does not exist."""


class RollbackFailedError(ExecutionError):
    """Raised when a rollback operation fails."""


class ResumeFailedError(ExecutionError):
    """Raised when resuming from a checkpoint fails."""


class PlanValidationError(ExecutionError):
    """Raised when an execution plan is invalid."""


class ExecutorNotFoundError(ExecutionError):
    """Raised when no executor is registered for an action."""


class ExecutionPausedError(ExecutionError):
    """Raised when trying to execute on a paused plan."""


class ExecutionTimeoutError(ExecutionError):
    """Raised when a step exceeds its timeout."""
