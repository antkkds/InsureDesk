"""Base rule class and helpers for all validation rules."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from src.portal.validation.models import (
    RuleStatus,
    ValidationContext,
    ValidationRule,
)

# Registry of known context section names for field resolution
CONTEXT_SECTIONS = {"customer", "quote", "form_data", "portal_state"}


def get_field_value(
    context: ValidationContext, field_path: Optional[str]
) -> Any:
    """Resolve a field value from context.

    Supports two formats:
    1. "customer.name" — section-specific: looks in context.customer["name"]
    2. "name" — flat: tries all sections in order

    Also handles nested paths like "customer.address.city".
    """
    if not field_path:
        return None

    parts = field_path.split(".")
    first = parts[0]

    if first in CONTEXT_SECTIONS:
        # Section-specific: "customer.name" → context.customer["name"]
        section = getattr(context, first, {})
        if not isinstance(section, dict):
            return None
        if len(parts) == 1:
            return section
        value = section
        for key in parts[1:]:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value
    else:
        # Flat path: try each section in order
        for section_name in ("customer", "quote", "form_data"):
            section = getattr(context, section_name, {})
            if not isinstance(section, dict):
                continue
            value = section
            for key in parts:
                if isinstance(value, dict):
                    value = value.get(key)
                else:
                    value = None
                    break
            if value is not None:
                return value
        return None


@dataclass
class BaseRule(ValidationRule):
    """Convenience base class with common helpers."""

    def validate(self, context: ValidationContext) -> RuleStatus:
        """Override in subclasses."""
        raise NotImplementedError

    def fail(self) -> RuleStatus:
        return RuleStatus.FAILED

    def pass_(self) -> RuleStatus:
        return RuleStatus.PASSED

    def get_value(self, context: ValidationContext) -> Any:
        return get_field_value(context, self.field)
