"""Portal Validation Engine.

Validates insurance portal data before and after execution.
Sits between ExecutionEngine and QuoteExecutor.

Architecture:
    ExecutionEngine
        |
        v
    ValidationEngine  ← Sprint 4.2
        |
        +-- Business Rules (age, IC, occupation, premium)
        +-- Portal Adapter (error messages, page state)
        |
        v
    QuoteExecutor
"""

from __future__ import annotations

from src.portal.validation.models import (
    ValidationContext,
    ValidationResult,
    ValidationError,
    ValidationWarning,
    ValidationRule,
    RuleStatus,
    Severity,
)
from src.portal.validation.engine import ValidationEngine
from src.portal.validation.registry import ValidationRuleRegistry
from src.portal.validation.loader import ValidationLoader
from src.portal.validation.adapters.portal_validation import (
    PortalValidationAdapter,
)
from src.portal.validation.exceptions import (
    ValidationError_,
    ValidationFailedError,
    RuleExecutionError,
    RuleNotFoundError,
    ValidationConfigError,
    PortalValidationAdapterError,
)

__all__ = [
    "ValidationContext",
    "ValidationResult",
    "ValidationError",
    "ValidationWarning",
    "ValidationRule",
    "RuleStatus",
    "Severity",
    "ValidationEngine",
    "ValidationRuleRegistry",
    "ValidationLoader",
    "PortalValidationAdapter",
    "ValidationError_",
    "ValidationFailedError",
    "RuleExecutionError",
    "RuleNotFoundError",
    "ValidationConfigError",
    "PortalValidationAdapterError",
]
