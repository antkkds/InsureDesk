"""AgeRule — validates applicant age is within allowed range."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from src.portal.validation.models import RuleStatus, ValidationContext
from src.portal.validation.rules.base import BaseRule


@dataclass
class AgeRule(BaseRule):
    """Validates age is between min and max.

    Config:
        min_age: Minimum allowed age (default: 0)
        max_age: Maximum allowed age (default: 999)
        date_field: Field name for DOB (default: uses self.field)
    """

    min_age: int = 0
    max_age: int = 999
    date_field: Optional[str] = None

    def validate(self, context: ValidationContext) -> RuleStatus:
        field = self.date_field or self.field
        if not field:
            return RuleStatus.ERROR

        value = self.get_value(context)

        if value is None:
            return self.fail()

        age = self._to_age(value)
        if age is None:
            return RuleStatus.ERROR

        if age < self.min_age or age > self.max_age:
            self.metadata["message"] = (
                f"Age must be between {self.min_age} and {self.max_age} "
                f"(got {age})"
            )
            return self.fail()

        return self.pass_()

    @staticmethod
    def _to_age(value) -> Optional[int]:
        """Convert various date/age formats to age integer."""
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str):
            try:
                parts = value.split("-")
                if len(parts) == 3:
                    birth = date(int(parts[0]), int(parts[1]), int(parts[2]))
                    today = date.today()
                    return today.year - birth.year - (
                        (today.month, today.day) < (birth.month, birth.day)
                    )
            except (ValueError, IndexError):
                pass
            try:
                return int(value)
            except ValueError:
                pass
        return None
