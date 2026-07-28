"""Portal Validation Engine — Rule Registry.

Manages registration and discovery of validation rules.
Rules can be registered programmatically or loaded from YAML configs.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Type

from src.portal.validation.models import ValidationRule
from src.portal.validation.exceptions import RuleNotFoundError

logger = logging.getLogger("insuredesk.validation.registry")


class ValidationRuleRegistry:
    """Registry for validation rule types and instances.

    Two-level system:
    1. Rule classes are registered by type name (e.g. "age", "ic")
    2. Rule instances are created from config and stored

    Usage:
        registry = ValidationRuleRegistry()

        # Register a rule class
        registry.register_type("age", AgeRule)

        # Create rule instances from config
        registry.add_rule(AgeRule(id="age_check", min_age=18, max_age=65))

        # Get rules for a specific context
        rules = registry.get_rules(portal="great_eastern", action="create_quote")
    """

    def __init__(self) -> None:
        self._rule_types: Dict[str, Type[ValidationRule]] = {}
        self._rules: Dict[str, ValidationRule] = {}
        self._portal_rules: Dict[str, Dict[str, List[str]]] = {}
        # ^ {portal: {action: [rule_id, ...]}}

    def register_type(self, type_name: str, rule_class: Type[ValidationRule]) -> None:
        """Register a rule class by type name."""
        self._rule_types[type_name] = rule_class
        logger.debug("Registered rule type '%s'", type_name)

    def get_type(self, type_name: str) -> Type[ValidationRule]:
        """Get a rule class by type name."""
        cls = self._rule_types.get(type_name)
        if cls is None:
            raise RuleNotFoundError(
                f"No rule type registered for '{type_name}'. "
                f"Available: {list(self._rule_types.keys())}"
            )
        return cls

    def add_rule(self, rule: ValidationRule) -> None:
        """Register a rule instance."""
        self._rules[rule.id] = rule
        logger.debug("Added rule '%s' (%s)", rule.id, type(rule).__name__)

    def add_portal_rule(
        self, portal: str, action: str, rule_id: str
    ) -> None:
        """Associate a rule with a portal + action."""
        if portal not in self._portal_rules:
            self._portal_rules[portal] = {}
        if action not in self._portal_rules[portal]:
            self._portal_rules[portal][action] = []
        if rule_id not in self._portal_rules[portal][action]:
            self._portal_rules[portal][action].append(rule_id)

    def get_rules(
        self,
        portal: Optional[str] = None,
        action: Optional[str] = None,
    ) -> List[ValidationRule]:
        """Get all rules for a portal + action combination."""
        rule_ids: List[str] = []

        # Get portal-specific rules
        if portal and portal in self._portal_rules:
            if action and action in self._portal_rules[portal]:
                rule_ids.extend(self._portal_rules[portal][action])
            # Also include rules registered for '*' wildcard action
            if "*" in self._portal_rules.get(portal, {}):
                rule_ids.extend(self._portal_rules[portal]["*"])

        # Return matching rules
        return [self._rules[rid] for rid in rule_ids if rid in self._rules]

    def get_all_rules(self) -> List[ValidationRule]:
        """Get all registered rule instances."""
        return list(self._rules.values())

    def get_rule(self, rule_id: str) -> Optional[ValidationRule]:
        """Get a specific rule by ID."""
        return self._rules.get(rule_id)

    def remove_rule(self, rule_id: str) -> None:
        """Remove a rule instance."""
        self._rules.pop(rule_id, None)
        # Also clean up portal mappings
        for portal in self._portal_rules:
            for action in list(self._portal_rules[portal]):
                if rule_id in self._portal_rules[portal][action]:
                    self._portal_rules[portal][action].remove(rule_id)

    def has_type(self, type_name: str) -> bool:
        return type_name in self._rule_types

    def list_types(self) -> List[str]:
        return list(self._rule_types.keys())

    def clear(self) -> None:
        self._rule_types.clear()
        self._rules.clear()
        self._portal_rules.clear()
