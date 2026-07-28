"""Portal Validation Engine — Exceptions."""

from __future__ import annotations


class ValidationError_(Exception):
    """Base exception for validation errors."""


class ValidationFailedError(ValidationError_):
    """Raised when validation fails (blocking errors present)."""


class RuleExecutionError(ValidationError_):
    """Raised when a rule itself fails to execute."""


class RuleNotFoundError(ValidationError_):
    """Raised when a requested rule is not registered."""


class ValidationConfigError(ValidationError_):
    """Raised when validation configuration is invalid."""


class PortalValidationAdapterError(ValidationError_):
    """Raised when portal validation adapter encounters an error."""
