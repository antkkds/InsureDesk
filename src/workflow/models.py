"""InsureDesk — Workflow: Data Models.

Models for the end-to-end quote workflow orchestrator.
Ties together UIP-AI request, portal interaction, validation, and review.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ══════════════════════════════════════════════════════════════════
# Quote Request / Response
# ══════════════════════════════════════════════════════════════════


class QuoteStatus(Enum):
    """Lifecycle of a quote workflow execution."""

    PENDING = "pending"
    REQUEST_RECEIVED = "request_received"
    VALIDATING_INPUT = "validating_input"
    PORTAL_LOGIN = "portal_login"
    CREATING_QUOTE = "creating_quote"
    VALIDATING_QUOTE = "validating_quote"
    REVIEWING = "reviewing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    APPROVAL_PENDING = "approval_pending"


class ApprovalLevel(Enum):
    """Required approval level for an action."""

    NONE = "none"  # Execute automatically
    RECOMMENDED = "recommended"  # AI suggests, auto-execute with note
    REQUIRED = "required"  # Must be approved before execution


@dataclass
class QuoteRequest:
    """A quote creation request from UIP-AI or API.

    Fields are deliberately flat and generic — mapping to
    portal-specific YAML fields happens inside QuoteExecutor.
    """

    portal_id: str = "great_eastern"
    workflow: str = "quote"
    customer_name: str = ""
    customer_ic: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    customer_dob: str = ""

    # Coverage details
    sum_insured: float = 0.0
    sum_insured_building: float = 0.0
    sum_insured_contents: float = 0.0
    property_address: str = ""
    property_postcode: str = ""
    property_city: str = ""
    property_state: str = ""
    occupancy: str = ""
    occupancy_class: str = ""
    construction_type: str = ""
    year_built: int = 0
    number_of_floors: int = 0
    building_area: float = 0.0
    building_type: str = ""
    roof_type: str = ""
    security_features: str = ""
    coverage_start: str = ""
    coverage_end: str = ""

    # Metadata
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    customer_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "QuoteRequest":
        """Create from a dict (typically from UIP-AI bridge request)."""
        known = {
            k for k in cls.__dataclass_fields__
            if k not in ("metadata", "conversation_id", "session_id", "customer_id")
        }
        result = cls()
        for key, value in d.items():
            if key in known:
                setattr(result, key, value)
        # Merge unknown keys into metadata
        result.metadata = {k: v for k, v in d.items() if k not in known}
        result.conversation_id = d.get("conversation_id")
        result.session_id = d.get("session_id")
        result.customer_id = d.get("customer_id")
        return result

    def to_dict(self) -> dict:
        return {
            "portal_id": self.portal_id,
            "workflow": self.workflow,
            "customer_name": self.customer_name,
            "customer_ic": self.customer_ic,
            "customer_email": self.customer_email,
            "customer_phone": self.customer_phone,
            "customer_dob": self.customer_dob,
            "sum_insured": self.sum_insured,
            "sum_insured_building": self.sum_insured_building,
            "sum_insured_contents": self.sum_insured_contents,
            "property_address": self.property_address,
            "property_postcode": self.property_postcode,
            "property_city": self.property_city,
            "property_state": self.property_state,
            "occupancy": self.occupancy,
            "occupancy_class": self.occupancy_class,
            "construction_type": self.construction_type,
            "year_built": self.year_built,
            "number_of_floors": self.number_of_floors,
            "building_area": self.building_area,
            "building_type": self.building_type,
            "roof_type": self.roof_type,
            "security_features": self.security_features,
            "coverage_start": self.coverage_start,
            "coverage_end": self.coverage_end,
        }

    def is_valid(self) -> bool:
        """Minimum fields needed for a valid quote request."""
        if not self.portal_id:
            return False
        if not self.customer_name and not self.customer_ic:
            return False
        if self.sum_insured <= 0 and self.sum_insured_building <= 0:
            return False
        return True

    def missing_fields(self) -> List[str]:
        """Return list of missing critical fields."""
        missing = []
        if not self.customer_name:
            missing.append("customer_name")
        if not self.customer_ic:
            missing.append("customer_ic")
        if self.sum_insured <= 0 and self.sum_insured_building <= 0:
            missing.append("sum_insured or sum_insured_building")
        return missing


@dataclass
class QuoteResponse:
    """Structured result from a completed quote workflow."""

    workflow_id: str = ""
    portal_id: str = ""
    status: QuoteStatus = QuoteStatus.PENDING
    premium_amount: float = 0.0
    coverage_summary: str = ""
    premium_breakdown: Dict[str, float] = field(default_factory=dict)
    policy_terms: str = ""
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    validation_passed: bool = False
    review_summary: str = ""
    execution_duration_ms: float = 0.0
    raw_portal_response: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    @property
    def succeeded(self) -> bool:
        return self.status == QuoteStatus.COMPLETED and self.premium_amount > 0

    @property
    def human_summary(self) -> str:
        """Human-readable one-liner."""
        if self.succeeded:
            return (
                f"✅ Quote for {self.portal_id}: RM {self.premium_amount:,.2f} "
                f"({self.coverage_summary or 'no details'})"
            )
        if self.status == QuoteStatus.APPROVAL_PENDING:
            return f"⏳ Quote for {self.portal_id} — approval pending"
        return f"❌ Quote failed: {', '.join(self.errors[:3]) or 'unknown error'}"


# ══════════════════════════════════════════════════════════════════
# Workflow Session
# ══════════════════════════════════════════════════════════════════


@dataclass
class WorkflowStep:
    """A single step in a workflow execution."""

    name: str = ""
    status: str = "pending"  # pending, running, success, failed
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None


@dataclass
class WorkflowSession:
    """Tracks the full lifecycle of a quote workflow execution."""

    id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:8]}")
    portal_id: str = ""
    status: QuoteStatus = QuoteStatus.PENDING
    steps: List[WorkflowStep] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    conversation_id: Optional[str] = None
    session_id: Optional[str] = None
    customer_id: Optional[str] = None
    request: Optional[QuoteRequest] = None
    response: Optional[QuoteResponse] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_step(self, name: str) -> "WorkflowStep":
        step = WorkflowStep(name=name, status="pending")
        self.steps.append(step)
        return step

    def mark_step_running(self, name: str) -> None:
        for step in self.steps:
            if step.name == name and step.status == "pending":
                step.status = "running"
                step.started_at = datetime.now().isoformat()
                break
        self.updated_at = datetime.now().isoformat()

    def mark_step_completed(self, name: str, result: dict = None) -> None:
        now = datetime.now()
        for step in self.steps:
            if step.name == name and step.status == "running":
                step.status = "success"
                step.completed_at = now.isoformat()
                if step.started_at:
                    start = datetime.fromisoformat(step.started_at)
                    step.duration_ms = (now - start).total_seconds() * 1000
                step.result = result
                break
        self.updated_at = now.isoformat()

    def mark_step_failed(self, name: str, error: str) -> None:
        for step in self.steps:
            if step.name == name and step.status == "running":
                step.status = "failed"
                step.completed_at = datetime.now().isoformat()
                step.error = error
                break
        self.updated_at = datetime.now().isoformat()
        self.error = error

    def update_status(self, status: QuoteStatus) -> None:
        self.status = status
        self.updated_at = datetime.now().isoformat()

    @property
    def duration_ms(self) -> float:
        if not self.steps:
            return 0.0
        return sum(s.duration_ms for s in self.steps if s.status == "success")


# ══════════════════════════════════════════════════════════════════
# Approval Gate (Phase 6.2 prep)
# ══════════════════════════════════════════════════════════════════


@dataclass
class ActionApprovalRule:
    """Defines what approval level is needed for an action."""

    action: str
    approval: ApprovalLevel
    max_amount: float = 0.0  # 0 = no amount limit
    description: str = ""


# Pre-defined approval matrix for insurance portal actions
DEFAULT_APPROVAL_MATRIX: List[ActionApprovalRule] = [
    ActionApprovalRule(
        action="search_policy",
        approval=ApprovalLevel.NONE,
        description="Search policy by IC or policy number",
    ),
    ActionApprovalRule(
        action="generate_quote",
        approval=ApprovalLevel.RECOMMENDED,
        description="Generate a new insurance quote",
    ),
    ActionApprovalRule(
        action="save_draft",
        approval=ApprovalLevel.REQUIRED,
        description="Save quote as draft",
    ),
    ActionApprovalRule(
        action="submit_application",
        approval=ApprovalLevel.REQUIRED,
        description="Submit insurance application",
    ),
    ActionApprovalRule(
        action="submit_claim",
        approval=ApprovalLevel.REQUIRED,
        description="Submit insurance claim",
    ),
    ActionApprovalRule(
        action="issue_policy",
        approval=ApprovalLevel.REQUIRED,
        description="Issue new policy",
    ),
]


class ApprovalGate:
    """Evaluates whether an action needs human approval before execution."""

    def __init__(self, rules: Optional[List[ActionApprovalRule]] = None):
        self._rules = rules if rules is not None else DEFAULT_APPROVAL_MATRIX
        self._rules_map = {r.action: r for r in self._rules}

    def check(self, action: str, amount: float = 0.0) -> ActionApprovalRule:
        """Check approval level for an action.

        Returns the matching rule. Caller decides action based on
        the approval level.
        """
        rule = self._rules_map.get(action)
        if not rule:
            return ActionApprovalRule(
                action=action,
                approval=ApprovalLevel.REQUIRED,
                description="Unknown action — require approval",
            )
        return rule

    def needs_approval(self, action: str, amount: float = 0.0) -> bool:
        """Returns True if this action needs human approval."""
        rule = self.check(action, amount)
        if rule.approval == ApprovalLevel.NONE:
            return False
        if rule.approval == ApprovalLevel.RECOMMENDED:
            return False  # Recommended = auto-execute
        if rule.approval == ApprovalLevel.REQUIRED:
            if rule.max_amount > 0 and amount > rule.max_amount:
                return True
            return True
        return True

    def requires_confirmation(self, action: str, amount: float = 0.0) -> bool:
        """Returns True if this action needs a confirmation notice."""
        rule = self.check(action, amount)
        return rule.approval in (ApprovalLevel.RECOMMENDED, ApprovalLevel.REQUIRED)
