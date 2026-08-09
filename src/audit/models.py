"""InsureDesk — Audit: Data Models.

Core data structures for production audit trail,
sensitive data protection, and approval logging.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class AuditLevel(Enum):
    """Severity/importance of an audit event."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AuditCategory(Enum):
    """Category of audit event."""

    WORKFLOW = "workflow"
    EXECUTION = "execution"
    LOGIN = "login"
    QUOTE = "quote"
    VALIDATION = "validation"
    REVIEW = "review"
    APPROVAL = "approval"
    SECURITY = "security"
    CREDENTIAL = "credential"
    DATA_ACCESS = "data_access"
    SYSTEM = "system"


@dataclass
class AuditEntry:
    """A single auditable event in the system.

    Each entry captures one atomic action with enough context
    to investigate failures, trace usage, and support compliance.
    """

    id: str = field(default_factory=lambda: f"audit_{uuid.uuid4().hex[:8]}")
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    level: AuditLevel = AuditLevel.INFO
    category: AuditCategory = AuditCategory.SYSTEM
    action: str = ""
    actor: str = ""  # agent_id, user_id, or "system"
    portal_id: str = ""
    workflow_id: str = ""
    execution_id: str = ""
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    sensitive: bool = False  # True if this entry has redacted sensitive fields
    duration_ms: float = 0.0
    error: Optional[str] = None

    @property
    def summary(self) -> str:
        if self.error:
            return f"[{self.level.value.upper()}] {self.action}: {self.error}"
        return f"[{self.level.value.upper()}] {self.action} — {self.message[:100]}"


@dataclass
class AuditQuery:
    """Query parameters for searching audit entries."""

    level: Optional[AuditLevel] = None
    category: Optional[AuditCategory] = None
    action: Optional[str] = None
    actor: Optional[str] = None
    portal_id: Optional[str] = None
    workflow_id: Optional[str] = None
    execution_id: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    has_error: Optional[bool] = None
    limit: int = 100
    offset: int = 0


@dataclass
class ApprovalDecision:
    """Record of a human approval decision."""

    id: str = field(default_factory=lambda: f"aprv_{uuid.uuid4().hex[:8]}")
    action: str = ""
    workflow_id: str = ""
    portal_id: str = ""
    requested_by: str = ""
    approved_by: str = ""
    decision: str = ""  # approved, rejected, pending
    reason: str = ""
    amount: float = 0.0
    requested_at: str = field(default_factory=lambda: datetime.now().isoformat())
    decided_at: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


# Sensitive field patterns — paths that should be masked in logs
SENSITIVE_FIELD_PATTERNS: List[str] = [
    "customer_ic",
    "ic_number",
    "customer_ic",
    "passport",
    "password",
    "token",
    "credential",
    "secret",
    "api_key",
    "phone",
    "customer_phone",
    "customer_email",
    "email",
    "dob",
    "customer_dob",
]

# Fields to mask completely (show nothing)
REDACTED_FIELDS: List[str] = [
    "password",
    "token",
    "credential",
    "secret",
    "api_key",
]

# Fields to mask partially (show last 4 chars)
PARTIAL_MASK_FIELDS: List[str] = [
    "customer_ic",
    "ic_number",
    "phone",
    "customer_phone",
    "passport",
]
