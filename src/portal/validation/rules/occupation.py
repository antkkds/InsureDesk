"""OccupationRule — validates occupation against allowed/blocked lists."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from src.portal.validation.models import RuleStatus, ValidationContext
from src.portal.validation.rules.base import BaseRule


@dataclass
class OccupationRule(BaseRule):
    """Validates occupation against allowed and blocked lists.

    Config:
        allowed: List of allowed occupations (empty = all allowed)
        blocked: List of blocked occupations (empty = none blocked)
        case_sensitive: If False, comparison is case-insensitive (default: False)
    """

    allowed: List[str] = field(default_factory=list)
    blocked: List[str] = field(default_factory=list)
    case_sensitive: bool = False

    def validate(self, context: ValidationContext) -> RuleStatus:
        value = self.get_value(context)

        if value is None or not isinstance(value, str):
            return self.fail()

        occupation = value if self.case_sensitive else value.strip().lower()
        allowed = (
            [o.lower() for o in self.allowed]
            if not self.case_sensitive
            else self.allowed
        )
        blocked = (
            [b.lower() for b in self.blocked]
            if not self.case_sensitive
            else self.blocked
        )

        if blocked and occupation in blocked:
            self.metadata["message"] = f"Occupation '{value}' is not allowed"
            return self.fail()

        if allowed and occupation not in allowed:
            self.metadata["message"] = (
                f"Occupation '{value}' is not in the allowed list"
            )
            return self.fail()

        return self.pass_()
