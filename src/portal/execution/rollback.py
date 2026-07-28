"""Portal Execution Engine — Rollback Manager.

Handles rolling back steps that have failed during execution.
Rollback lets each step define a reverse action that undoes its work.

ExecutionEngine calls RollbackManager when a step fails and the
plan has rollback actions defined for completed steps.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.execution.exceptions import RollbackFailedError
from src.portal.execution.models import (
    ExecutionContext,
    ExecutionPlan,
    ExecutionStep,
    StepStatus,
)
from src.portal.execution.registry import ExecutorRegistry

logger = logging.getLogger("insuredesk.execution.rollback")


class RollbackManager:
    """Manages rollback of execution steps.

    Usage:
        rollback_mgr = RollbackManager(registry)
        success = rollback_mgr.rollback_to(plan, context, failed_step_index)
    """

    def __init__(self, registry: ExecutorRegistry):
        self._registry = registry

    def rollback_to(
        self,
        plan: ExecutionPlan,
        context: ExecutionContext,
        failed_step_index: int,
    ) -> bool:
        """Roll back all steps after the failure point.

        Walks backwards through completed steps and executes their
        rollback_action if defined. Steps without a rollback_action
        are skipped.

        Args:
            plan: The execution plan
            context: Current execution context
            failed_step_index: Index of the step that failed

        Returns:
            True if all rollbacks succeeded, False otherwise
        """
        # Find steps to roll back (completed after the failed step)
        steps_to_rollback = []
        for i in range(failed_step_index - 1, -1, -1):
            step = plan.steps[i]
            if step.status == StepStatus.SUCCESS and step.rollback_action:
                steps_to_rollback.append(step)

        if not steps_to_rollback:
            logger.info("No rollback actions to execute for plan '%s'", plan.name)
            plan.is_failed = True
            return True

        all_success = True
        for step in steps_to_rollback:
            try:
                logger.info(
                    "Rolling back step '%s' via action '%s'",
                    step.name,
                    step.rollback_action,
                )
                executor = self._registry.resolve(step.rollback_action)
                executor(context, step)
                step.status = StepStatus.ROLLED_BACK
            except Exception as e:
                logger.error(
                    "Rollback failed for step '%s': %s", step.name, e
                )
                all_success = False
                step.metadata["rollback_error"] = str(e)

        plan.is_failed = not all_success
        if not all_success:
            plan.metadata["rollback_errors"] = [
                s.metadata.get("rollback_error", "unknown")
                for s in steps_to_rollback
                if "rollback_error" in s.metadata
            ]

        return all_success

    def can_rollback(self, plan: ExecutionPlan, step_index: int) -> bool:
        """Check if rollback is possible for the given step."""
        for i in range(step_index - 1, -1, -1):
            step = plan.steps[i]
            if step.status == StepStatus.SUCCESS and step.rollback_action:
                try:
                    self._registry.resolve(step.rollback_action)
                    return True
                except Exception:
                    continue
        return False
