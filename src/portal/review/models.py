"""Portal Review Engine — Data Models.

Core data structures for the review and explainability layer.
Transforms execution + validation results into human/AI-readable summaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as data_field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from src.portal.validation.models import ValidationResult


class ReviewStatus(Enum):
    """Overall review status."""
    APPROVED = "approved"
    WARNING = "warning"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class ChangeType(Enum):
    """Type of field change detected."""
    CREATED = "created"
    UPDATED = "updated"
    REMOVED = "removed"
    NORMALIZED = "normalized"
    AUTO_FIXED = "auto_fixed"
    UNCHANGED = "unchanged"


@dataclass
class Change:
    """A single field-level change detected during execution."""

    field: str = ""
    before: Any = None
    after: Any = None
    change_type: str = "updated"
    source: str = "portal"  # 'portal', 'system', 'user', 'auto_fix'
    reason: Optional[str] = None
    severity: str = "info"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "before": self.before,
            "after": self.after,
            "change_type": self.change_type,
            "source": self.source,
            "reason": self.reason,
            "severity": self.severity,
        }


@dataclass
class ReviewIssue:
    """An issue detected during review (error or warning)."""

    rule_id: str = ""
    field: Optional[str] = None
    message: str = ""
    severity: str = "warning"  # 'error' or 'warning'
    category: str = "business"  # 'business', 'portal', 'execution'
    suggested_action: Optional[str] = None
    metadata: Dict[str, Any] = data_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
            "category": self.category,
            "suggested_action": self.suggested_action,
        }


@dataclass
class Suggestion:
    """An auto-fix or improvement suggestion."""

    field: str = ""
    message: str = ""
    current_value: Any = None
    suggested_value: Any = None
    confidence: float = 1.0  # 0.0 to 1.0
    auto_fixable: bool = False
    requires_approval: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "field": self.field,
            "message": self.message,
            "current_value": self.current_value,
            "suggested_value": self.suggested_value,
            "confidence": self.confidence,
            "auto_fixable": self.auto_fixable,
            "requires_approval": self.requires_approval,
        }


@dataclass
class ReviewContext:
    """Input context for a review run.

    Contains all data needed to produce a comprehensive review:
    - Before/after data snapshots
    - Validation results
    - Execution results
    """

    execution_id: str = data_field(
        default_factory=lambda: f"review_{uuid.uuid4().hex[:12]}"
    )
    portal: str = ""
    action: str = ""
    before_data: Dict[str, Any] = data_field(default_factory=dict)
    after_data: Dict[str, Any] = data_field(default_factory=dict)
    validation_result: Optional[ValidationResult] = None
    execution_errors: List[str] = data_field(default_factory=list)
    metadata: Dict[str, Any] = data_field(default_factory=dict)

    @property
    def has_validation(self) -> bool:
        return self.validation_result is not None

    @property
    def has_errors(self) -> bool:
        if self.validation_result and not self.validation_result.passed:
            return True
        return len(self.execution_errors) > 0


@dataclass
class ReviewResult:
    """Structured review output.

    The primary output of the ReviewEngine.
    Designed to be serialized directly for Bridge Protocol communication.
    """

    execution_id: str = ""
    status: str = "approved"
    changes: List[Change] = data_field(default_factory=list)
    errors: List[ReviewIssue] = data_field(default_factory=list)
    warnings: List[ReviewIssue] = data_field(default_factory=list)
    suggestions: List[Suggestion] = data_field(default_factory=list)
    requires_human_review: bool = False
    summary: str = ""
    created_at: Optional[datetime] = None

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0

    @property
    def has_issues(self) -> bool:
        return len(self.errors) > 0 or len(self.warnings) > 0

    def add_change(self, change: Change) -> None:
        self.changes.append(change)

    def add_error(self, issue: ReviewIssue) -> None:
        self.errors.append(issue)
        if self.status in ("approved", "warning"):
            self.status = "failed"
        self.requires_human_review = True

    def add_warning(self, issue: ReviewIssue) -> None:
        self.warnings.append(issue)
        if self.status == "approved":
            self.status = "warning"

    def add_suggestion(self, suggestion: Suggestion) -> None:
        self.suggestions.append(suggestion)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for Bridge Protocol."""
        return {
            "execution_id": self.execution_id,
            "status": self.status,
            "summary": self.summary,
            "changes": [c.to_dict() for c in self.changes],
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
            "suggestions": [s.to_dict() for s in self.suggestions],
            "requires_human_review": self.requires_human_review,
            "has_changes": self.has_changes,
            "has_issues": self.has_issues,
        }
