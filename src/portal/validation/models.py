"""Portal Validation Engine — Data Models.

Core data structures for insurance portal validation.
Business validation vs Portal validation distinction is maintained
through separate rule categories and adapters.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field as data_field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Severity(Enum):
    """Severity level for validation results."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class RuleStatus(Enum):
    """Status of a single validation rule execution."""
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class ValidationError:
    """A single validation error with structured context."""

    rule_id: str = ""
    field: Optional[str] = None
    message: str = ""
    severity: str = "error"
    category: str = "business"  # 'business' or 'portal'
    value: Any = None
    expected: Any = None
    metadata: Dict[str, Any] = data_field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
            "category": self.category,
            "value": self.value,
            "expected": self.expected,
        }


@dataclass
class ValidationWarning:
    """A non-blocking validation warning."""

    rule_id: str = ""
    message: str = ""
    field: Optional[str] = None
    category: str = "business"
    metadata: Dict[str, Any] = data_field(default_factory=dict)


@dataclass
class ValidationContext:
    """Input context for a validation run.

    Contains all data needed by validation rules to evaluate
    business rules and portal state checks.
    """

    execution_id: str = data_field(
        default_factory=lambda: f"val_{uuid.uuid4().hex[:12]}"
    )
    portal: str = ""
    action: str = ""
    customer: Dict[str, Any] = data_field(default_factory=dict)
    quote: Dict[str, Any] = data_field(default_factory=dict)
    form_data: Dict[str, Any] = data_field(default_factory=dict)
    portal_state: Dict[str, Any] = data_field(default_factory=dict)
    metadata: Dict[str, Any] = data_field(default_factory=dict)

    def get_customer_field(self, key: str, default: Any = None) -> Any:
        """Get a customer field by dot-path or direct key."""
        return self._get_nested(self.customer, key, default)

    def get_quote_field(self, key: str, default: Any = None) -> Any:
        """Get a quote field by dot-path or direct key."""
        return self._get_nested(self.quote, key, default)

    def get_form_field(self, key: str, default: Any = None) -> Any:
        """Get a form data field by dot-path or direct key."""
        return self._get_nested(self.form_data, key, default)

    @staticmethod
    def _get_nested(data: Dict, path: str, default: Any = None) -> Any:
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return default
        return current if current is not None else default


@dataclass
class ValidationResult:
    """Structured result from a validation run.

    passed: True only if NO errors (warnings don't block).
    errors: List of ValidationError (blocking).
    warnings: List of ValidationWarning (non-blocking).
    executed_rules: Names of rules that ran.
    """

    passed: bool = True
    errors: List[ValidationError] = data_field(default_factory=list)
    warnings: List[ValidationWarning] = data_field(default_factory=list)
    executed_rules: List[str] = data_field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def add_error(self, error: ValidationError) -> None:
        self.errors.append(error)
        self.passed = False

    def add_warning(self, warning: ValidationWarning) -> None:
        self.warnings.append(warning)

    def merge(self, other: ValidationResult) -> None:
        """Merge another result into this one."""
        self.errors.extend(other.errors)
        self.warnings.extend(other.warnings)
        self.executed_rules.extend(other.executed_rules)
        if not other.passed:
            self.passed = False

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [
                {"rule_id": w.rule_id, "message": w.message}
                for w in self.warnings
            ],
            "executed_rules": self.executed_rules,
            "error_count": self.error_count,
            "warning_count": self.warning_count,
        }


@dataclass
class ValidationRule:
    """Base class for all validation rules.

    Subclass this to implement specific rule types.
    Each rule evaluates a single condition and returns a RuleResult.

    Categories:
    - business: Insurance domain knowledge (age, IC, occupation, premium)
    - portal: Portal-specific checks (field errors, session state)
    """

    id: str = ""
    name: str = ""
    category: str = "business"
    severity: str = "error"
    enabled: bool = True
    field: Optional[str] = None
    metadata: Dict[str, Any] = data_field(default_factory=dict)

    def validate(self, context: ValidationContext) -> RuleStatus:
        """Execute this rule against the given context.

        Must be overridden by subclasses.
        Returns RuleStatus.PASSED or RuleStatus.FAILED.
        On failure, raises ValidationError via context or returns status.
        """
        raise NotImplementedError

    def should_skip(self, context: ValidationContext) -> bool:
        """Determine if this rule should be skipped for this context."""
        return not self.enabled


@dataclass
class RuleDefinition:
    """YAML-deserialized rule definition before instantiation."""

    id: str = ""
    type: str = ""
    severity: str = "error"
    field: Optional[str] = None
    enabled: bool = True
    params: Dict[str, Any] = data_field(default_factory=dict)
