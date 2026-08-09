"""RequiredFieldRule — checks that required fields are present and non-empty."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.portal.validation.models import RuleStatus, ValidationContext
from src.portal.validation.rules.base import BaseRule, get_field_value


@dataclass
class RequiredFieldRule(BaseRule):
    """Validates that required fields are present and non-empty.

    Config:
        fields: List of field paths to check (overrides self.field)
        allow_empty: If True, empty strings are accepted (default: False)
    """

    fields: List[str] = field(default_factory=list)
    allow_empty: bool = False

    def validate(self, context: ValidationContext) -> RuleStatus:
        fields_to_check = self.fields or ([self.field] if self.field else [])

        for field_path in fields_to_check:
            value = get_field_value(context, field_path)
            if value is None:
                return self.fail()
            if isinstance(value, str) and not value.strip():
                if not self.allow_empty:
                    return self.fail()
                continue
            if not self.allow_empty and value == "":
                return self.fail()

        return self.pass_()
