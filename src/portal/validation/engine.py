"""Portal Validation Engine — ValidationEngine.

The central orchestrator that runs validation rules against a context.
Coordinates business rules and portal validation adapters.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.portal.validation.models import (
    RuleStatus,
    ValidationContext,
    ValidationError,
    ValidationResult,
    ValidationRule,
    ValidationWarning,
)
from src.portal.validation.registry import ValidationRuleRegistry
from src.portal.validation.exceptions import (
    ValidationFailedError,
    RuleExecutionError,
)

logger = logging.getLogger("insuredesk.validation.engine")


class ValidationEngine:
    """Executes validation rules against a given context.

    Usage:
        engine = ValidationEngine(registry)

        # Run all rules for a portal + action
        result = engine.validate(context, portal="great_eastern", action="create_quote")

        # Run specific rules only
        result = engine.validate_rules(context, [rule1, rule2])
    """

    def __init__(self, registry: ValidationRuleRegistry):
        self._registry = registry

    def validate(
        self,
        context: ValidationContext,
        portal: Optional[str] = None,
        action: Optional[str] = None,
    ) -> ValidationResult:
        """Run all applicable rules for a portal + action.

        Args:
            context: The validation context with customer/quote/form data
            portal: Portal name to filter rules
            action: Action name to filter rules

        Returns:
            ValidationResult with errors, warnings, and status
        """
        rules = self._registry.get_rules(portal=portal, action=action)
        return self.validate_rules(context, rules)

    def validate_rules(
        self,
        context: ValidationContext,
        rules: List[ValidationRule],
    ) -> ValidationResult:
        """Run a specific set of rules against the context.

        Args:
            context: Validation context
            rules: List of rule instances to execute

        Returns:
            ValidationResult
        """
        result = ValidationResult(started_at=datetime.now())

        for rule in rules:
            if rule.should_skip(context):
                result.executed_rules.append(f"{rule.id}:skipped")
                continue

            try:
                status = rule.validate(context)
                result.executed_rules.append(f"{rule.id}:{status.value}")

                if status == RuleStatus.FAILED:
                    error = ValidationError(
                        rule_id=rule.id,
                        field=rule.field,
                        message=self._get_error_message(rule, context),
                        severity=rule.severity,
                        category=rule.category,
                    )
                    result.add_error(error)
                elif status == RuleStatus.ERROR:
                    error = ValidationError(
                        rule_id=rule.id,
                        message=f"Rule '{rule.id}' encountered an internal error",
                        severity="error",
                        category=rule.category,
                    )
                    result.add_error(error)

            except RuleExecutionError as e:
                logger.warning("Rule '%s' execution error: %s", rule.id, e)
                error = ValidationError(
                    rule_id=rule.id,
                    message=str(e),
                    severity="error",
                    category=rule.category,
                )
                result.add_error(error)

            except Exception as e:
                logger.error("Rule '%s' unexpected error: %s", rule.id, e)
                error = ValidationError(
                    rule_id=rule.id,
                    message=f"Rule '{rule.id}' internal error: {e}",
                    severity="error",
                    category=rule.category,
                )
                result.add_error(error)

        result.completed_at = datetime.now()
        return result

    def validate_or_raise(
        self,
        context: ValidationContext,
        portal: Optional[str] = None,
        action: Optional[str] = None,
        rules: Optional[List[ValidationRule]] = None,
    ) -> ValidationResult:
        """Validate and raise if there are blocking errors.

        Returns the result if passed, raises ValidationFailedError if not.

        WARNING-level errors do NOT block execution.
        ERROR-level errors block execution.
        """
        if rules is not None:
            result = self.validate_rules(context, rules)
        else:
            result = self.validate(context, portal=portal, action=action)
        if not result.passed:
            raise ValidationFailedError(
                f"Validation failed for {portal}/{action}: "
                f"{result.error_count} error(s), {result.warning_count} warning(s)"
            )
        return result

    def get_registry(self) -> ValidationRuleRegistry:
        """Get the underlying registry for direct manipulation."""
        return self._registry

    @staticmethod
    def _get_error_message(rule: ValidationRule, context: ValidationContext) -> str:
        """Get a default error message for a failed rule."""
        if rule.metadata and "message" in rule.metadata:
            return rule.metadata["message"]
        return f"Rule '{rule.id}' failed"
