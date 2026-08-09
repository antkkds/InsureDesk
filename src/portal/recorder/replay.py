"""Portal Workflow Recorder — Replay Engine.

Replays recorded workflows through the ExecutionEngine.
Converts Workflow steps into ExecutionSteps and executes them.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.recorder.models import Workflow, WorkflowStep
from src.portal.recorder.exceptions import ReplayError
from src.portal.execution.models import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionResult,
    ExecutionStep,
    RetryPolicy,
    StepStatus,
)
from src.portal.execution.engine import ExecutionEngine
from src.portal.execution.registry import ExecutorRegistry

logger = logging.getLogger("insuredesk.recorder.replay")


class ReplayEngine:
    """Converts Workflows into executable ExecutionPlans.

    Usage:
        replay = ReplayEngine(execution_engine)
        result = replay.execute_workflow(workflow, context)
    """

    def __init__(self, execution_engine: ExecutionEngine):
        self._execution_engine = execution_engine

    def to_execution_plan(
        self,
        workflow: Workflow,
        data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionPlan:
        """Convert a Workflow into an ExecutionPlan.

        Each WorkflowStep becomes one ExecutionStep.

        Args:
            workflow: The workflow to convert
            data: Optional input data

        Returns:
            An ExecutionPlan ready for ExecutionEngine
        """
        steps: List[ExecutionStep] = []
        for ws in workflow.steps:
            step = ExecutionStep(
                name=f"{ws.action}_{len(steps) + 1:02d}",
                action=ws.action,
                parameters=dict(ws.parameters),
                checkpoint_enabled=ws.checkpoint,
                retry_policy=self._retry_policy_from_step(ws),
            )
            # Add wait time as metadata
            if ws.wait_after_ms != 500:
                step.metadata["wait_after_ms"] = ws.wait_after_ms
            steps.append(step)

        plan = ExecutionPlan(
            name=workflow.name or f"{workflow.portal}_replay",
            portal=workflow.portal,
            steps=steps,
            metadata={
                "source": "workflow_recorder",
                "workflow_id": workflow.id,
                "input_data": data or {},
            },
        )
        return plan

    def execute_workflow(
        self,
        workflow: Workflow,
        data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Execute a recorded workflow.

        This is the main entry point for replaying a workflow.

        Args:
            workflow: The recorded workflow to replay
            data: Optional input data for the execution

        Returns:
            ExecutionResult from the ExecutionEngine
        """
        plan = self.to_execution_plan(workflow, data)
        context = ExecutionContext(
            plan_id=plan.id,
            portal=workflow.portal,
            variables=data or {},
        )
        result = self._execution_engine.execute(plan, context)

        logger.info(
            "Workflow '%s' replayed: success=%s, %d steps",
            workflow.name, result.success, len(result.completed_steps),
        )
        return result

    def execute_workflow_with_resume(
        self,
        workflow: Workflow,
        data: Optional[Dict[str, Any]] = None,
    ) -> ExecutionResult:
        """Execute a workflow with checkpoint resume support."""
        plan = self.to_execution_plan(workflow, data)
        return self._execution_engine.execute_with_resume(plan)

    @staticmethod
    def _retry_policy_from_step(
        step: WorkflowStep,
    ) -> RetryPolicy:
        """Extract retry policy from workflow step config."""
        if step.retry_policy:
            return RetryPolicy(
                max_retries=step.retry_policy.get("max_retries", 3),
                delay_seconds=step.retry_policy.get("delay_seconds", 2.0),
                backoff_multiplier=step.retry_policy.get("backoff", 2.0),
            )
        return RetryPolicy(max_retries=2, delay_seconds=1.0)
