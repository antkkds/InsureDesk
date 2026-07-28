"""Portal Execution Engine — ExecutionEngine.

The central orchestrator that manages the lifecycle of an execution plan.

ExecutionEngine does NOT know about:
- Specific portals (Great Eastern, AIA, etc.)
- Browser automation details
- Insurance domain rules

It ONLY manages:
- Step lifecycle (PENDING → RUNNING → SUCCESS/FAILED)
- Checkpoint saving at step boundaries
- Retry logic for transient failures
- Rollback on unrecoverable failures
- Resume from checkpoints

The actual work is delegated to registered executors via ExecutorRegistry.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from src.portal.execution.checkpoint import CheckpointManager, MemoryCheckpointStore
from src.portal.execution.exceptions import (
    ExecutionPausedError,
    ExecutionTimeoutError,
    StepExecutionError,
)
from src.portal.execution.models import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStep,
    StepStatus,
)
from src.portal.execution.plan import PlanBuilder
from src.portal.execution.registry import ExecutorRegistry
from src.portal.execution.resume import ResumeManager
from src.portal.execution.rollback import RollbackManager

logger = logging.getLogger("insuredesk.execution.engine")


class ExecutionEngine:
    """Central orchestrator for portal execution plans.

    Usage:
        engine = ExecutionEngine(registry)

        # Execute a plan synchronously
        result = engine.execute(plan, context)

        # Execute with resume support
        result = engine.execute_with_resume(plan_id)

        # Step-by-step control
        engine.start(plan, context)
        while plan.next_step():
            engine.step(plan, context)
        result = engine.finish(plan, context)
    """

    def __init__(
        self,
        registry: ExecutorRegistry,
        plan_builder: Optional[PlanBuilder] = None,
        checkpoint_manager: Optional[CheckpointManager] = None,
    ):
        self._registry = registry
        self._plan_builder = plan_builder or PlanBuilder()
        self._ckpt_mgr = checkpoint_manager or CheckpointManager(MemoryCheckpointStore())
        self._resume_mgr = ResumeManager(self._ckpt_mgr)
        self._rollback_mgr = RollbackManager(registry)

    # ── High-level API ──

    def execute(
        self,
        plan: ExecutionPlan,
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """Execute a plan from start to finish.

        This is the main entry point for synchronous execution.
        Handles checkpointing, retries, and rollback automatically.

        Args:
            plan: The execution plan to run
            context: Optional pre-built context (created fresh if None)

        Returns:
            ExecutionResult with structured business output
        """
        if context is None:
            context = self._create_context(plan)

        plan.started_at = datetime.now()
        context.started_at = plan.started_at

        try:
            step = plan.next_step()
            while step is not None:
                self._execute_step(plan, context, step)
                step = plan.next_step()

            plan.is_completed = True
            plan.completed_at = datetime.now()
            return self._build_result(plan, context, success=True)

        except Exception as e:
            logger.error("Execution failed for plan '%s': %s", plan.id, e)
            plan.is_failed = True
            plan.completed_at = datetime.now()
            return self._build_result(plan, context, success=False, error=str(e))

    def execute_with_resume(
        self,
        plan: ExecutionPlan,
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionResult:
        """Execute a plan, attempting to resume from checkpoint if available.

        If a checkpoint exists for this plan, resumes from there.
        Otherwise starts fresh.

        Args:
            plan: The execution plan
            context: Optional execution context

        Returns:
            ExecutionResult
        """
        restored_ctx = self._resume_mgr.resume(plan)
        if restored_ctx is not None:
            logger.info("Resumed plan '%s' from checkpoint", plan.id)
            context = restored_ctx
        return self.execute(plan, context)

    # ── Step-by-step API ──

    def start(
        self,
        plan: ExecutionPlan,
        context: Optional[ExecutionContext] = None,
    ) -> ExecutionContext:
        """Initialise and return the execution context."""
        if context is None:
            context = self._create_context(plan)
        plan.started_at = datetime.now()
        context.started_at = plan.started_at
        logger.info("Started execution: %s (%d steps)", plan.name, len(plan.steps))
        return context

    def step(self, plan: ExecutionPlan, context: ExecutionContext) -> ExecutionStep:
        """Execute the next pending step.

        Returns the executed step (with updated status).
        Raises StopIteration if no more steps.
        """
        step = plan.next_step()
        if step is None:
            raise StopIteration("No more pending steps")
        self._execute_step(plan, context, step)
        return step

    def finish(self, plan: ExecutionPlan, context: ExecutionContext) -> ExecutionResult:
        """Finalise execution and return the result."""
        plan.completed_at = datetime.now()
        success = not plan.is_failed and not any(
            s.status == StepStatus.FAILED for s in plan.steps
        )
        plan.is_completed = success
        return self._build_result(plan, context, success=success)

    # ── Internal ──

    def _create_context(self, plan: ExecutionPlan) -> ExecutionContext:
        return ExecutionContext(
            plan_id=plan.id,
            portal=plan.portal,
            variables=dict(plan.metadata.get("source_data", {})),
        )

    def _execute_step(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        step: ExecutionStep,
    ) -> None:
        """Execute a single step with retry and checkpoint support."""
        if plan.is_paused:
            raise ExecutionPausedError(f"Plan '{plan.id}' is paused")

        step.status = StepStatus.RUNNING
        step.started_at = datetime.now()
        context.current_step_id = step.id
        logger.info("Executing step: %s (action=%s)", step.name, step.action)

        executor = self._registry.resolve(step.action)
        last_error: Optional[str] = None

        for attempt in range(step.retry_policy.max_retries + 1):
            try:
                if attempt > 0:
                    delay = self._compute_delay(attempt, step.retry_policy)
                    logger.info(
                        "Retry %d/%d for step '%s' in %.1fs",
                        attempt, step.retry_policy.max_retries,
                        step.name, delay,
                    )
                    time.sleep(delay)
                    step.retry_count = attempt

                start = time.monotonic()
                result = executor(context, step)
                elapsed = time.monotonic() - start

                if step.timeout_seconds and elapsed > step.timeout_seconds:
                    raise ExecutionTimeoutError(
                        f"Step '{step.name}' exceeded timeout of {step.timeout_seconds}s"
                    )

                # Success
                step.status = StepStatus.SUCCESS
                step.result = result if isinstance(result, dict) else {"value": result}
                step.completed_at = datetime.now()
                plan.current_step_index = plan.steps.index(step) + 1

                # Update context with step results
                if step.result:
                    context.update(step.result)

                # Save checkpoint
                if step.checkpoint_enabled:
                    self._ckpt_mgr.save_checkpoint(plan, context)

                logger.info("Step '%s' completed successfully", step.name)
                return

            except Exception as e:
                last_error = str(e)
                logger.warning(
                    "Step '%s' failed (attempt %d/%d): %s",
                    step.name, attempt + 1,
                    step.retry_policy.max_retries + 1, e,
                )
                # Check if we should retry
                if not self._should_retry(e, step.retry_policy):
                    break

        # All retries exhausted
        step.status = StepStatus.FAILED
        step.error = last_error
        step.completed_at = datetime.now()
        logger.error("Step '%s' failed after %d attempts: %s",
                     step.name, step.retry_count + 1, last_error)

        # Attempt rollback
        self._rollback_mgr.rollback_to(plan, context, plan.steps.index(step))

        raise StepExecutionError(
            f"Step '{step.name}' failed: {last_error}"
        )

    def _should_retry(self, error: Exception, policy: Any) -> bool:
        """Determine if an error is retryable."""
        if policy.max_retries == 0:
            return False
        error_name = type(error).__name__
        for retryable in policy.retryable_exceptions:
            if retryable in error_name or retryable in str(error):
                return True
        return False

    def _compute_delay(self, attempt: int, policy: Any) -> float:
        """Compute delay with exponential backoff."""
        delay = policy.delay_seconds * (policy.backoff_multiplier ** (attempt - 1))
        return min(delay, policy.max_delay_seconds)

    def _build_result(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        success: bool = True,
        error: Optional[str] = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=success,
            execution_id=context.execution_id,
            plan_id=plan.id,
            data=dict(context.variables),
            errors=[error] if error else [],
            warnings=[],
            completed_steps=[
                s.name for s in plan.steps
                if s.status in (StepStatus.SUCCESS, StepStatus.SKIPPED)
            ],
            started_at=plan.started_at,
            completed_at=plan.completed_at,
        )

    # ── Plan management ──

    def create_plan(
        self,
        portal: str,
        action: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """Create an execution plan from a business request."""
        return self._plan_builder.build(portal, action, data)
