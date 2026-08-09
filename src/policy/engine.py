"""InsureDesk — Policy Engine.

Business rules layer that sits between the LLM Assistant and Tool Execution.

Architecture:
    AI Decision → Policy Check → Tool Execution

Each policy rule defines:
- What action/scenario it applies to
- Conditions that trigger the rule
- Effect: ALLOW, DENY, REQUIRE_APPROVAL, or WARN

Policies are YAML-configurable for easy customer setup.

Usage:
    from src.policy.engine import PolicyEngine, PolicyEffect

    engine = PolicyEngine()
    engine.add_rule(PolicyRule(
        name="quote_submit_requires_approval",
        action="quote.submit",
        effect=PolicyEffect.REQUIRE_APPROVAL,
        reason="Submitting quotes requires human confirmation.",
    ))

    result = engine.evaluate("quote.submit", {"premium": 5000})
    if result.effect == PolicyEffect.DENY:
        print(f"Blocked: {result.reason}")
"""

from __future__ import annotations

from typing import Optional, Any, Dict, List
from dataclasses import dataclass, field
from enum import Enum


# ══════════════════════════════════════════════════════════════════
# Policy Effect
# ══════════════════════════════════════════════════════════════════


class PolicyEffect(Enum):
    """Possible outcomes of a policy evaluation."""
    ALLOW = "allow"                     # Action is permitted
    DENY = "deny"                       # Action is blocked
    REQUIRE_APPROVAL = "require_approval"  # Needs human confirmation
    WARN = "warn"                       # Allowed but with warning


# ══════════════════════════════════════════════════════════════════
# Policy Rule
# ══════════════════════════════════════════════════════════════════


@dataclass
class PolicyCondition:
    """A condition that must be met for a rule to apply.

    Supports:
    - field == value (exact match)
    - field > value (numeric comparison)
    - field < value (numeric comparison)
    - field >= value
    - field <= value
    - field in [values] (list membership)
    """
    field: str                          # Context field path (e.g. "premium")
    operator: str                       # ==, >, <, >=, <=, in
    value: Any                          # Value to compare against


@dataclass
class PolicyRule:
    """A single business policy rule.

    A rule applies when ALL its conditions match.
    The most severe effect wins when multiple rules match.
    """
    name: str                           # Unique rule name
    action: str                         # Action pattern (e.g. "quote.*", "quote.submit")
    effect: PolicyEffect                # What to do when rule matches
    reason: str = ""                    # Human-readable explanation
    conditions: List[PolicyCondition] = field(default_factory=list)
    priority: int = 0                   # Higher = evaluated first (0 = default)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ══════════════════════════════════════════════════════════════════
# Policy Result
# ══════════════════════════════════════════════════════════════════


@dataclass
class PolicyResult:
    """Result of evaluating policies for an action."""
    effect: PolicyEffect = PolicyEffect.ALLOW
    reason: str = ""
    matched_rules: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    requires_approval_from: List[str] = field(default_factory=list)

    @property
    def is_allowed(self) -> bool:
        return self.effect in (PolicyEffect.ALLOW, PolicyEffect.WARN)

    @property
    def is_blocked(self) -> bool:
        return self.effect == PolicyEffect.DENY

    @property
    def needs_approval(self) -> bool:
        return self.effect == PolicyEffect.REQUIRE_APPROVAL


# ══════════════════════════════════════════════════════════════════
# Policy Engine
# ══════════════════════════════════════════════════════════════════


class PolicyEngine:
    """Evaluates business policies for tool actions.

    Rules are evaluated in order of descending priority.
    The most severe effect (DENY > REQUIRE_APPROVAL > WARN > ALLOW) wins.

    Usage:
        engine = PolicyEngine()
        engine.add_rule(PolicyRule(
            name="no_submit", action="quote.submit",
            effect=PolicyEffect.DENY,
            reason="Submission is disabled in this environment.",
        ))

        result = engine.evaluate("quote.submit", {"premium": 10000})
        if result.is_blocked:
            print(f"Blocked: {result.reason}")
    """

    def __init__(self):
        self._rules: List[PolicyRule] = []

    def add_rule(self, rule: PolicyRule) -> None:
        """Add a policy rule.

        Args:
            rule: The PolicyRule to add.
        """
        self._rules.append(rule)
        # Keep sorted by priority descending
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def add_rules(self, rules: List[PolicyRule]) -> None:
        """Add multiple rules at once."""
        for rule in rules:
            self.add_rule(rule)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name. Returns True if found."""
        before = len(self._rules)
        self._rules = [r for r in self._rules if r.name != name]
        return len(self._rules) < before

    def clear_rules(self) -> None:
        """Remove all rules."""
        self._rules.clear()

    def list_rules(self) -> List[dict]:
        """List all rules (sorted by priority)."""
        return [
            {
                "name": r.name,
                "action": r.action,
                "effect": r.effect.value,
                "reason": r.reason,
                "conditions": len(r.conditions),
                "priority": r.priority,
            }
            for r in self._rules
        ]

    def count(self) -> int:
        """Number of registered rules."""
        return len(self._rules)

    def evaluate(self, action: str,
                 context: Optional[Dict[str, Any]] = None) -> PolicyResult:
        """Evaluate all rules for a given action.

        Args:
            action: Action name to evaluate (e.g. "quote.submit").
            context: Context data for condition evaluation.

        Returns:
            PolicyResult with the most severe matching effect.
        """
        context = context or {}
        result = PolicyResult(effect=PolicyEffect.ALLOW)

        for rule in self._rules:
            if not _action_matches(rule.action, action):
                continue

            if not _conditions_met(rule.conditions, context):
                continue

            # Rule matches — update result
            result.matched_rules.append(rule.name)

            if rule.effect == PolicyEffect.DENY:
                result.effect = PolicyEffect.DENY
                result.reason = rule.reason
                return result  # Immediate denial

            elif rule.effect == PolicyEffect.REQUIRE_APPROVAL:
                if self._severity(result.effect) < self._severity(PolicyEffect.REQUIRE_APPROVAL):
                    result.effect = PolicyEffect.REQUIRE_APPROVAL
                    result.reason = rule.reason
                    if "approver" in rule.metadata:
                        result.requires_approval_from.append(rule.metadata["approver"])

            elif rule.effect == PolicyEffect.WARN:
                if self._severity(result.effect) < self._severity(PolicyEffect.WARN):
                    result.effect = PolicyEffect.WARN
                result.warnings.append(rule.reason)

        return result

    @staticmethod
    def _severity(effect: PolicyEffect) -> int:
        """Severity ranking for comparing effects."""
        ranking = {
            PolicyEffect.ALLOW: 0,
            PolicyEffect.WARN: 1,
            PolicyEffect.REQUIRE_APPROVAL: 2,
            PolicyEffect.DENY: 3,
        }
        return ranking.get(effect, 0)


# ══════════════════════════════════════════════════════════════════
# Matching helpers
# ══════════════════════════════════════════════════════════════════


def _action_matches(rule_pattern: str, action: str) -> bool:
    """Check if an action matches a rule pattern.

    Supports:
    - Exact match: "quote.submit" == "quote.submit"
    - Wildcard: "quote.*" matches "quote.calculate", "quote.submit"
    """
    if rule_pattern == "*":
        return True
    if rule_pattern == action:
        return True
    if rule_pattern.endswith(".*"):
        prefix = rule_pattern[:-2]
        return action.startswith(prefix)
    return False


def _conditions_met(conditions: List[PolicyCondition],
                    context: Dict[str, Any]) -> bool:
    """Check if ALL conditions are met given the context.

    Returns True if no conditions (vacuously true).
    """
    if not conditions:
        return True

    for cond in conditions:
        actual = _get_nested(context, cond.field)

        if cond.operator == "==":
            if actual != cond.value:
                return False

        elif cond.operator == "!=":
            if actual == cond.value:
                return False

        elif cond.operator == ">":
            if not (isinstance(actual, (int, float)) and actual > cond.value):
                return False

        elif cond.operator == "<":
            if not (isinstance(actual, (int, float)) and actual < cond.value):
                return False

        elif cond.operator == ">=":
            if not (isinstance(actual, (int, float)) and actual >= cond.value):
                return False

        elif cond.operator == "<=":
            if not (isinstance(actual, (int, float)) and actual <= cond.value):
                return False

        elif cond.operator == "in":
            if not (isinstance(cond.value, list) and actual in cond.value):
                return False

        elif cond.operator == "contains":
            if not (isinstance(actual, str) and cond.value in actual):
                return False

        else:
            raise ValueError(f"Unknown operator: {cond.operator}")

    return True


def _get_nested(context: dict, field: str) -> Any:
    """Get a nested field value from context dict.

    Supports dot notation: "customer.name" -> context["customer"]["name"]
    """
    parts = field.split(".")
    value = context
    for part in parts:
        if isinstance(value, dict):
            value = value.get(part, None)
        else:
            return None
    return value
