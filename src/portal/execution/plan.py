"""Portal Execution Engine — Plan Builder.

Generates an ExecutionPlan from an incoming business request.
The PlanBuilder translates high-level requests (e.g. "create quote for GEGLink")
into a sequence of ExecutionSteps with proper ordering and dependencies.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.execution.models import (
    ExecutionPlan,
    ExecutionStep,
    RetryPolicy,
    StepStatus,
)
from src.portal.execution.exceptions import PlanValidationError

logger = logging.getLogger("insuredesk.execution.plan")

# Known action templates for common insurance tasks
DEFAULT_PLAN_TEMPLATES: Dict[str, List[Dict[str, Any]]] = {
    "create_quote": [
        {"name": "login", "action": "login", "checkpoint_enabled": True},
        {
            "name": "navigate_to_quote",
            "action": "navigate",
            "parameters": {"page": "quotation"},
            "checkpoint_enabled": True,
        },
        {
            "name": "fill_customer_details",
            "action": "fill",
            "parameters": {"mapping": "customer"},
            "checkpoint_enabled": True,
            "retry_policy": "fast",
        },
        {
            "name": "fill_risk_details",
            "action": "fill",
            "parameters": {"mapping": "risk"},
            "checkpoint_enabled": True,
            "retry_policy": "fast",
        },
        {
            "name": "calculate_premium",
            "action": "calculate",
            "checkpoint_enabled": False,
        },
        {
            "name": "capture_result",
            "action": "capture",
            "parameters": {"outputs": ["premium", "quote_no"]},
            "checkpoint_enabled": True,
        },
    ],
    "renew_policy": [
        {"name": "login", "action": "login", "checkpoint_enabled": True},
        {
            "name": "search_policy",
            "action": "search",
            "parameters": {"search_by": "policy_no"},
            "checkpoint_enabled": True,
        },
        {
            "name": "open_renewal",
            "action": "navigate",
            "parameters": {"page": "renewal"},
            "checkpoint_enabled": True,
        },
        {
            "name": "review_details",
            "action": "review",
            "checkpoint_enabled": True,
        },
        {
            "name": "confirm_renewal",
            "action": "submit",
            "checkpoint_enabled": True,
            "rollback_action": "cancel_renewal",
        },
    ],
}


class PlanBuilder:
    """Builds ExecutionPlans from business requests."""

    def __init__(self, templates: Optional[Dict[str, List[Dict[str, Any]]]] = None):
        self._templates = templates or DEFAULT_PLAN_TEMPLATES

    def build(
        self,
        portal: str,
        action: str,
        data: Optional[Dict[str, Any]] = None,
        plan_name: Optional[str] = None,
    ) -> ExecutionPlan:
        """Build an execution plan from a business request.

        Args:
            portal: Portal name (e.g. "great_eastern")
            action: Business action (e.g. "create_quote")
            data: Input data for the action
            plan_name: Optional custom plan name

        Returns:
            A fully populated ExecutionPlan

        Raises:
            PlanValidationError: If the action has no template
        """
        template = self._templates.get(action)
        if template is None:
            raise PlanValidationError(
                f"No plan template found for action '{action}'. "
                f"Available templates: {list(self._templates.keys())}"
            )

        steps = []
        for i, step_def in enumerate(template):
            retry_policy = self._parse_retry_policy(step_def.get("retry_policy"))
            step = ExecutionStep(
                name=step_def["name"],
                action=step_def["action"],
                parameters=step_def.get("parameters", {}),
                retry_policy=retry_policy,
                checkpoint_enabled=step_def.get("checkpoint_enabled", True),
                rollback_action=step_def.get("rollback_action"),
                rollback_parameters=step_def.get("rollback_parameters", {}),
                depends_on=step_def.get("depends_on", []),
                timeout_seconds=step_def.get("timeout_seconds"),
            )
            steps.append(step)

        # Auto-wire dependencies if not explicitly set
        self._auto_wire_dependencies(steps)

        plan_name = plan_name or f"{portal}:{action}"

        plan = ExecutionPlan(
            name=plan_name,
            portal=portal,
            steps=steps,
            metadata={"source_action": action, "source_data": data or {}},
        )
        return plan

    def register_template(
        self, action: str, steps: List[Dict[str, Any]]
    ) -> None:
        """Register or replace a plan template."""
        self._templates[action] = steps
        logger.info("Registered plan template for '%s' (%d steps)", action, len(steps))

    def _parse_retry_policy(self, value: Any) -> RetryPolicy:
        if isinstance(value, RetryPolicy):
            return value
        if isinstance(value, str):
            return {
                "no_retry": RetryPolicy.no_retry(),
                "fast": RetryPolicy.fast(),
                "aggressive": RetryPolicy.aggressive(),
            }.get(value, RetryPolicy())
        return RetryPolicy()

    def _auto_wire_dependencies(self, steps: List[ExecutionStep]) -> None:
        """Auto-set depends_on based on step ordering."""
        for i, step in enumerate(steps):
            if not step.depends_on and i > 0:
                step.depends_on = [steps[i - 1].id]

    def list_templates(self) -> List[str]:
        """Return available template names."""
        return list(self._templates.keys())
