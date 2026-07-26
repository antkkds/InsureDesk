"""InsureDesk — Insurance Task / Workflow Model.

Connects Assistant Runtime with Domain Model.
An InsuranceTask tracks what needs to happen next.
"""

from __future__ import annotations

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from .base import BaseModel


class TaskType(Enum):
    """Types of insurance workflow tasks."""
    RENEW_POLICY = "renew_policy"
    SUBMIT_CLAIM = "submit_claim"
    FOLLOW_UP_CLAIM = "follow_up_claim"
    UPDATE_CUSTOMER_INFO = "update_customer_info"
    REQUEST_DOCUMENT = "request_document"
    REVIEW_POLICY = "review_policy"
    QUOTE_REQUEST = "quote_request"
    ESCALATE = "escalate"
    UNKNOWN = "unknown"


class TaskAction(Enum):
    """What action the system should take next."""
    REQUEST_INPUT = "request_input"
    EXECUTE_AUTOMATION = "execute_automation"
    WAIT_FOR_PORTAL = "wait_for_portal"
    ESCALATE_HUMAN = "escalate_human"
    REVIEW_LLM = "review_llm"
    COMPLETED = "completed"


@dataclass
class WorkflowState(BaseModel):
    """Current state of an insurance workflow."""
    current_step: str = ""
    completed_steps: List[str] = field(default_factory=list)
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InsuranceTask(BaseModel):
    """An actionable task for the InsureDesk system.

    This is the bridge between Assistant Runtime and Domain Model.
    The runtime checks pending tasks, executes the next_action,
    and updates the task state.

    PortalAdapter and BrowserInspector feed into this:
    - Inspector finds the selectors → PortalAdapter fills them
    - PortalAdapter succeeds/fails → InsuranceTask updates
    """
    # ── Identification ──
    task_id: str = ""
    task_type: TaskType = TaskType.UNKNOWN

    # ── Target Entity ──
    policy_number: str = ""
    claim_id: str = ""
    customer_id: str = ""

    # ── State ──
    state: Optional[WorkflowState] = None
    next_action: TaskAction = TaskAction.REQUEST_INPUT
    status: str = "pending"          # pending, in_progress, completed, failed

    # ── Context ──
    missing_info: List[str] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)

    # ── Results ──
    result: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
