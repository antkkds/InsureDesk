"""Portal Execution Engine.

Orchestration layer for multi-step insurance portal workflows.
Builds on top of QuoteExecutor, NavigationEngine, and FillEngine
to provide lifecycle management, checkpointing, rollback, and resume.

This module does NOT replace existing code — it orchestrates it.
"""

from __future__ import annotations

from src.portal.execution.models import (
    ExecutionPlan,
    ExecutionStep,
    ExecutionContext,
    ExecutionResult,
    Checkpoint,
    RetryPolicy,
    StepStatus,
)
from src.portal.execution.engine import ExecutionEngine
from src.portal.execution.plan import PlanBuilder
from src.portal.execution.registry import ExecutorRegistry
from src.portal.execution.checkpoint import (
    CheckpointManager,
    CheckpointStore,
    MemoryCheckpointStore,
    SqliteCheckpointStore,
    CheckpointManager,
)
from src.portal.execution.rollback import RollbackManager
from src.portal.execution.resume import ResumeManager
from src.portal.execution.exceptions import (
    ExecutionError,
    StepExecutionError,
    CheckpointNotFoundError,
    RollbackFailedError,
    ResumeFailedError,
    PlanValidationError,
    ExecutorNotFoundError,
    ExecutionPausedError,
    ExecutionTimeoutError,
)

__all__ = [
    "ExecutionPlan",
    "ExecutionStep",
    "ExecutionContext",
    "ExecutionResult",
    "Checkpoint",
    "RetryPolicy",
    "StepStatus",
    "ExecutionEngine",
    "PlanBuilder",
    "ExecutorRegistry",
    "CheckpointManager",
    "CheckpointStore",
    "MemoryCheckpointStore",
    "SqliteCheckpointStore",
    "RollbackManager",
    "ResumeManager",
    "ExecutionError",
    "StepExecutionError",
    "CheckpointNotFoundError",
    "RollbackFailedError",
    "ResumeFailedError",
    "PlanValidationError",
    "ExecutorNotFoundError",
    "ExecutionPausedError",
    "ExecutionTimeoutError",
]
