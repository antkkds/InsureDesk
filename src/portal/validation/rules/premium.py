"""PremiumRule — validates premium amount against limits."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.portal.validation.models import RuleStatus, ValidationContext
from src.portal.validation.rules.base import BaseRule


@dataclass
class PremiumRule(BaseRule):
    """Validates premium amount is within allowed range.

    Config:
        min_premium: Minimum premium (default: 0)
        max_premium: Maximum premium (default: unlimited)
        currency: Currency code for display (default: "MYR")
    """

    min_premium: float = 0.0
    max_premium: Optional[float] = None
    currency: str = "MYR"

    def validate(self, context: ValidationContext) -> RuleStatus:
        value = self.get_value(context)

        if value is None:
            return self.fail()

        try:
            premium = float(value)
        except (TypeError, ValueError):
            return self.fail()

        if premium < self.min_premium:
            self.metadata["message"] = (
                f"Premium must be at least {self.currency} {self.min_premium:.2f} "
                f"(got {self.currency} {premium:.2f})"
            )
            return self.fail()

        if self.max_premium is not None and premium > self.max_premium:
            self.metadata["message"] = (
                f"Premium exceeds maximum of {self.currency} {self.max_premium:.2f} "
                f"(got {self.currency} {premium:.2f})"
            )
            return self.fail()

        return self.pass_()
