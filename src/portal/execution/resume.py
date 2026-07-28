"""Portal Execution Engine — Resume Manager.

Handles resuming execution from a checkpoint after a failure.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.portal.execution.checkpoint import CheckpointManager
from src.portal.execution.exceptions import ResumeFailedError
from src.portal.execution.models import (
    Checkpoint,
    ExecutionContext,
    ExecutionPlan,
    StepStatus,
)

logger = logging.getLogger("insuredesk.execution.resume")


class ResumeManager:
    """Manages resuming execution from checkpoints.

    Usage:
        resume_mgr = ResumeManager(checkpoint_mgr)
        plan, context = resume_mgr.resume(plan_id)
    """

    def __init__(self, checkpoint_manager: CheckpointManager):
        self._ckpt_mgr = checkpoint_manager

    def resume(
        self,
        plan: ExecutionPlan,
    ) -> Optional[ExecutionContext]:
        """Resume a plan from its latest checkpoint.

        Returns a restored ExecutionContext if a checkpoint exists,
        or None if there's nothing to resume from.

        The plan's steps are restored to their state at checkpoint time:
        - Steps before checkpoint: marked SUCCESS
        - The checkpoint step itself: reset to PENDING (will re-execute)
        - Steps after checkpoint: remain PENDING
        """
        checkpoint = self._ckpt_mgr.load_latest(plan.id)
        if checkpoint is None:
            logger.info("No checkpoint found for plan '%s'", plan.id)
            return None

        logger.info(
            "Resuming plan '%s' from checkpoint at step %d",
            plan.id,
            checkpoint.step_index,
        )

        # Restore context
        context = self._ckpt_mgr.restore_context(checkpoint, plan)

        # Reset the checkpoint step to PENDING (re-execute)
        if checkpoint.step_index < len(plan.steps):
            plan.steps[checkpoint.step_index].status = StepStatus.PENDING

        # Reset steps after checkpoint to PENDING
        for step in plan.steps[checkpoint.step_index + 1 :]:
            step.status = StepStatus.PENDING

        plan.is_failed = False
        plan.is_completed = False

        logger.info(
            "Plan '%s' resumed: %d/%d steps completed",
            plan.id,
            checkpoint.step_index,
            len(plan.steps),
        )
        return context

    def has_checkpoint(self, plan: ExecutionPlan) -> bool:
        """Check if a plan has a recoverable checkpoint."""
        ckpt = self._ckpt_mgr.load_latest(plan.id)
        return ckpt is not None
