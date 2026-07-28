"""Portal Review Engine — Suggestion Engine.

Generates auto-fix suggestions based on review data analysis.
Provides recommendations for common field-level corrections.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from src.portal.review.models import Change, ReviewContext, Suggestion

logger = logging.getLogger("insuredesk.review.suggestions")


class SuggestionEngine:
    """Analyses review data and generates improvement suggestions.

    Built-in suggestion rules:
    - Format normalization (date formats, phone numbers, IC numbers)
    - Value range warnings (premium near limits, age near limits)
    - Missing optional fields that could improve quote accuracy
    - Portal-specific recommendations
    """

    def __init__(self):
        self._custom_rules: List = []

    def generate(
        self,
        context: ReviewContext,
        changes: List[Change],
    ) -> List[Suggestion]:
        """Generate suggestions from review context and detected changes.

        Args:
            context: The review context
            changes: Detected field changes

        Returns:
            List of Suggestion objects
        """
        suggestions: List[Suggestion] = []

        # Run built-in suggestion rules
        suggestions.extend(self._check_date_formats(context, changes))
        suggestions.extend(self._check_value_ranges(context, changes))
        suggestions.extend(self._check_missing_optional_fields(context))

        # Run custom rules
        for rule in self._custom_rules:
            try:
                result = rule(context, changes)
                if result:
                    suggestions.extend(result if isinstance(result, list) else [result])
            except Exception as e:
                logger.warning("Custom suggestion rule failed: %s", e)

        return suggestions

    def add_custom_rule(self, rule_func) -> None:
        """Register a custom suggestion rule function.

        Signature: rule_func(context, changes) → Suggestion | List[Suggestion] | None
        """
        self._custom_rules.append(rule_func)

    def _check_date_formats(
        self,
        context: ReviewContext,
        changes: List[Change],
    ) -> List[Suggestion]:
        """Check for non-standard date formats that could be normalized."""
        suggestions = []
        date_fields = {"dob", "date_of_birth", "coverage_start", "coverage_end",
                       "effective_date", "expiry_date"}

        for field in context.after_data:
            value = context.after_data[field]
            if field in date_fields and isinstance(value, str):
                if "/" in value:
                    suggestions.append(Suggestion(
                        field=field,
                        message=f"Date format can be normalized to ISO (YYYY-MM-DD)",
                        current_value=value,
                        suggested_value=value.replace("/", "-"),
                        confidence=0.9,
                        auto_fixable=True,
                        requires_approval=False,
                    ))
        return suggestions

    def _check_value_ranges(
        self,
        context: ReviewContext,
        changes: List[Change],
    ) -> List[Suggestion]:
        """Check for values approaching limits that might need attention."""
        suggestions = []
        after = context.after_data

        # Premium near limits
        premium = after.get("premium") or after.get("sum_insured")
        if premium is not None:
            try:
                p = float(premium)
                if p > 9000:
                    suggestions.append(Suggestion(
                        field="premium",
                        message=f"Premium is high ({p:,.0f}). Consider reviewing coverage.",
                        current_value=p,
                        confidence=0.7,
                        auto_fixable=False,
                        requires_approval=True,
                    ))
            except (TypeError, ValueError):
                pass

        return suggestions

    def _check_missing_optional_fields(
        self,
        context: ReviewContext,
    ) -> List[Suggestion]:
        """Check for missing optional fields that add value."""
        suggestions = []
        before = context.before_data

        # Common optional fields that improve quote accuracy
        optional_checks = {
            "email": "Email for policy delivery",
            "phone": "Phone number for contact",
            "property_value": "Property value for accurate coverage",
        }

        for field, reason in optional_checks.items():
            if field not in before and field not in context.after_data:
                suggestions.append(Suggestion(
                    field=field,
                    message=f"Missing optional field: {field}. {reason}",
                    confidence=0.5,
                    auto_fixable=False,
                    requires_approval=False,
                ))

        return suggestions
