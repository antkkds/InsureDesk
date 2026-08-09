"""PortalValidationRule — handles portal-specific validation checks.

Unlike business rules, portal rules validate against browser/page state,
error messages, disabled buttons, and other UI-level signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.portal.validation.models import RuleStatus, ValidationContext
from src.portal.validation.rules.base import BaseRule


@dataclass
class PortalValidationRule(BaseRule):
    """Validates portal state (error messages, page state, etc.)

    This rule type checks the portal_state field in ValidationContext,
    which is populated by the PortalValidationAdapter.

    Config:
        check: Name of the portal check to perform
        expected: Expected value for the check
        error_selectors: CSS selectors for error elements to check
    """

    check: str = ""
    expected: Any = None
    error_selectors: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.category = "portal"

    def validate(self, context: ValidationContext) -> RuleStatus:
        portal_state = context.portal_state or {}

        if self.check:
            value = portal_state.get(self.check)
            if self.expected is not None and value != self.expected:
                self.metadata["message"] = (
                    f"Portal check '{self.check}' failed: "
                    f"expected {self.expected}, got {value}"
                )
                return self.fail()

        portal_errors = portal_state.get("errors", [])
        if portal_errors:
            self.metadata["message"] = f"Portal errors: {'; '.join(portal_errors[:3])}"
            return self.fail()

        if self.error_selectors:
            found_errors = portal_state.get("found_errors", [])
            if found_errors:
                self.metadata["message"] = (
                    f"Found {len(found_errors)} portal error(s)"
                )
                return self.fail()

        return self.pass_()
