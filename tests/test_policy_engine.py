"""Tests: Sprint 4 — Policy Engine.

Tests for:
1. PolicyEffect — enum values and helpers
2. PolicyCondition — condition evaluation
3. PolicyRule — rule data model
4. PolicyResult — result properties
5. PolicyEngine — rule management and evaluation
6. Integration with Tool Registry
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. PolicyEffect (3 tests)
# ══════════════════════════════════════════════════════════════════


class TestPolicyEffect:
    """PolicyEffect enum."""

    def test_values(self):
        from src.policy.engine import PolicyEffect
        assert PolicyEffect.ALLOW.value == "allow"
        assert PolicyEffect.DENY.value == "deny"
        assert PolicyEffect.REQUIRE_APPROVAL.value == "require_approval"
        assert PolicyEffect.WARN.value == "warn"

    def test_from_string(self):
        from src.policy.engine import PolicyEffect
        assert PolicyEffect("allow") == PolicyEffect.ALLOW
        assert PolicyEffect("deny") == PolicyEffect.DENY

    def test_all_defined(self):
        from src.policy.engine import PolicyEffect
        assert len(PolicyEffect) == 4


# ══════════════════════════════════════════════════════════════════
# 2. PolicyResult (4 tests)
# ══════════════════════════════════════════════════════════════════


class TestPolicyResult:
    """PolicyResult and its helper properties."""

    def test_default_is_allow(self):
        from src.policy.engine import PolicyResult, PolicyEffect
        r = PolicyResult()
        assert r.effect == PolicyEffect.ALLOW
        assert r.is_allowed is True
        assert r.is_blocked is False
        assert r.needs_approval is False

    def test_deny_properties(self):
        from src.policy.engine import PolicyResult, PolicyEffect
        r = PolicyResult(effect=PolicyEffect.DENY)
        assert r.is_allowed is False
        assert r.is_blocked is True
        assert r.needs_approval is False

    def test_require_approval_properties(self):
        from src.policy.engine import PolicyResult, PolicyEffect
        r = PolicyResult(effect=PolicyEffect.REQUIRE_APPROVAL)
        assert r.is_allowed is False
        assert r.is_blocked is False
        assert r.needs_approval is True

    def test_warn_is_allowed(self):
        from src.policy.engine import PolicyResult, PolicyEffect
        r = PolicyResult(effect=PolicyEffect.WARN)
        assert r.is_allowed is True
        assert r.is_blocked is False
        assert r.needs_approval is False


# ══════════════════════════════════════════════════════════════════
# 3. PolicyCondition (5 tests)
# ══════════════════════════════════════════════════════════════════


class TestPolicyCondition:
    """Condition evaluation."""

    def test_exact_match(self):
        from src.policy.engine import PolicyCondition, _conditions_met
        cond = PolicyCondition(field="premium", operator="==", value=5000)
        assert _conditions_met([cond], {"premium": 5000}) is True
        assert _conditions_met([cond], {"premium": 6000}) is False

    def test_not_equal(self):
        from src.policy.engine import PolicyCondition, _conditions_met
        cond = PolicyCondition(field="status", operator="!=", value="draft")
        assert _conditions_met([cond], {"status": "submitted"}) is True
        assert _conditions_met([cond], {"status": "draft"}) is False

    def test_greater_than(self):
        from src.policy.engine import PolicyCondition, _conditions_met
        cond = PolicyCondition(field="premium", operator=">", value=10000)
        assert _conditions_met([cond], {"premium": 15000}) is True
        assert _conditions_met([cond], {"premium": 5000}) is False

    def test_less_than_or_equal(self):
        from src.policy.engine import PolicyCondition, _conditions_met
        cond = PolicyCondition(field="premium", operator="<=", value=1000)
        assert _conditions_met([cond], {"premium": 500}) is True
        assert _conditions_met([cond], {"premium": 1000}) is True
        assert _conditions_met([cond], {"premium": 1500}) is False

    def test_in_list(self):
        from src.policy.engine import PolicyCondition, _conditions_met
        cond = PolicyCondition(field="risk_class", operator="in", value=["fire", "motor"])
        assert _conditions_met([cond], {"risk_class": "fire"}) is True
        assert _conditions_met([cond], {"risk_class": "motor"}) is True
        assert _conditions_met([cond], {"risk_class": "medical"}) is False

    def test_nested_field(self):
        from src.policy.engine import PolicyCondition, _conditions_met
        cond = PolicyCondition(field="customer.credit_score", operator=">", value=700)
        assert _conditions_met([cond], {"customer": {"credit_score": 750}}) is True
        assert _conditions_met([cond], {"customer": {"credit_score": 600}}) is False

    def test_empty_conditions_always_met(self):
        from src.policy.engine import _conditions_met
        assert _conditions_met([], {"anything": "value"}) is True


# ══════════════════════════════════════════════════════════════════
# 4. PolicyEngine — rule management (5 tests)
# ══════════════════════════════════════════════════════════════════


class TestPolicyEngineManagement:
    """Adding, removing, listing rules."""

    @pytest.fixture
    def engine(self):
        from src.policy.engine import PolicyEngine
        return PolicyEngine()

    def test_empty_engine_always_allows(self, engine):
        result = engine.evaluate("anything")
        assert result.effect.value == "allow"
        assert result.matched_rules == []

    def test_add_rule(self, engine):
        from src.policy.engine import PolicyRule, PolicyEffect
        engine.add_rule(PolicyRule(
            name="test_rule", action="test.action",
            effect=PolicyEffect.DENY, reason="Blocked",
        ))
        assert engine.count() == 1

    def test_add_multiple_rules(self, engine):
        from src.policy.engine import PolicyRule, PolicyEffect
        engine.add_rules([
            PolicyRule(name="r1", action="a1", effect=PolicyEffect.DENY),
            PolicyRule(name="r2", action="a2", effect=PolicyEffect.WARN),
            PolicyRule(name="r3", action="a3", effect=PolicyEffect.ALLOW),
        ])
        assert engine.count() == 3

    def test_remove_rule(self, engine):
        from src.policy.engine import PolicyRule, PolicyEffect
        engine.add_rule(PolicyRule(
            name="test", action="x", effect=PolicyEffect.DENY,
        ))
        assert engine.remove_rule("test") is True
        assert engine.count() == 0

    def test_remove_nonexistent_rule(self, engine):
        assert engine.remove_rule("nonexistent") is False

    def test_clear_rules(self, engine):
        from src.policy.engine import PolicyRule, PolicyEffect
        engine.add_rules([
            PolicyRule(name="r1", action="a1", effect=PolicyEffect.DENY),
            PolicyRule(name="r2", action="a2", effect=PolicyEffect.WARN),
        ])
        engine.clear_rules()
        assert engine.count() == 0

    def test_list_rules(self, engine):
        from src.policy.engine import PolicyRule, PolicyEffect
        engine.add_rule(PolicyRule(
            name="my_rule", action="quote.submit",
            effect=PolicyEffect.DENY, reason="No submissions allowed",
        ))
        rules = engine.list_rules()
        assert len(rules) == 1
        assert rules[0]["name"] == "my_rule"
        assert rules[0]["effect"] == "deny"


# ══════════════════════════════════════════════════════════════════
# 5. PolicyEngine — evaluation (12 tests)
# ══════════════════════════════════════════════════════════════════


class TestPolicyEngineEvaluation:
    """Policy evaluation logic."""

    @pytest.fixture
    def engine(self):
        from src.policy.engine import PolicyEngine, PolicyRule, PolicyEffect, PolicyCondition
        e = PolicyEngine()
        e.add_rules([
            PolicyRule(
                name="block_submit",
                action="quote.submit",
                effect=PolicyEffect.DENY,
                reason="Quote submission is disabled in read-only mode.",
            ),
            PolicyRule(
                name="high_premium_approval",
                action="quote.calculate",
                effect=PolicyEffect.REQUIRE_APPROVAL,
                reason="Quotes over RM 50,000 require manager approval.",
                conditions=[PolicyCondition(field="premium", operator=">", value=50000)],
                metadata={"approver": "manager"},
            ),
            PolicyRule(
                name="discount_limit",
                action="quote.calculate",
                effect=PolicyEffect.WARN,
                reason="Discount requested exceeds 15% max.",
                conditions=[PolicyCondition(field="discount", operator=">", value=15)],
            ),
            PolicyRule(
                name="block_high_risk_motor",
                action="quote.calculate",
                effect=PolicyEffect.DENY,
                reason="Motor quotes for high-risk drivers require manual underwriting.",
                conditions=[
                    PolicyCondition(field="risk_class", operator="in", value=["motor"]),
                    PolicyCondition(field="driver_age", operator="<", value=25),
                ],
            ),
        ])
        return e

    def test_no_match_returns_allow(self, engine):
        result = engine.evaluate("quote.list")
        assert result.effect.value == "allow"
        assert result.matched_rules == []

    def test_exact_action_match(self, engine):
        result = engine.evaluate("quote.submit")
        assert result.effect.value == "deny"
        assert "block_submit" in result.matched_rules
        assert result.reason == "Quote submission is disabled in read-only mode."

    def test_wildcard_action(self, engine):
        from src.policy.engine import PolicyEngine, PolicyRule, PolicyEffect, PolicyCondition
        e = PolicyEngine()
        e.add_rule(PolicyRule(
            name="block_all", action="*",
            effect=PolicyEffect.DENY, reason="Everything blocked.",
        ))
        result = e.evaluate("anything.at.all")
        assert result.effect.value == "deny"

    def test_wildcard_prefix(self, engine):
        from src.policy.engine import PolicyEngine, PolicyRule, PolicyEffect, PolicyCondition
        e = PolicyEngine()
        e.add_rule(PolicyRule(
            name="block_quote_actions", action="quote.*",
            effect=PolicyEffect.DENY, reason="All quote actions blocked.",
        ))
        assert e.evaluate("quote.submit").is_blocked
        assert e.evaluate("quote.calculate").is_blocked
        assert not e.evaluate("customer.create").is_blocked

    def test_condition_met(self, engine):
        result = engine.evaluate("quote.calculate", {"premium": 100000})
        assert result.needs_approval is True
        assert "high_premium_approval" in result.matched_rules

    def test_condition_not_met(self, engine):
        result = engine.evaluate("quote.calculate", {"premium": 10000})
        assert result.is_allowed is True
        assert "high_premium_approval" not in result.matched_rules

    def test_warn_effect(self, engine):
        result = engine.evaluate("quote.calculate", {"discount": 20})
        assert result.effect.value == "warn"
        assert "discount_limit" in result.matched_rules
        assert len(result.warnings) == 1

    def test_deny_overrides_warn(self, engine):
        """Both DENY and WARN match — DENY wins."""
        result = engine.evaluate("quote.calculate", {
            "premium": 100000,
            "discount": 20,
        })
        assert result.effect.value == "require_approval"
        # Premium condition is matched first due to priority ordering
        # But if both match, highest severity wins

    def test_multiple_conditions_all_met(self, engine):
        result = engine.evaluate("quote.calculate", {
            "risk_class": "motor",
            "driver_age": 20,
        })
        assert result.effect.value == "deny"
        assert "block_high_risk_motor" in result.matched_rules

    def test_multiple_conditions_one_not_met(self, engine):
        result = engine.evaluate("quote.calculate", {
            "risk_class": "motor",
            "driver_age": 30,
        })
        assert result.is_allowed is True
        assert "block_high_risk_motor" not in result.matched_rules

    def test_deny_is_immediate(self, engine):
        """DENY should short-circuit evaluation."""
        result = engine.evaluate("quote.submit")
        assert result.is_blocked is True

    def test_approver_in_metadata(self, engine):
        result = engine.evaluate("quote.calculate", {"premium": 100000})
        assert result.needs_approval is True
        assert "manager" in result.requires_approval_from

    def test_deny_premium_below_threshold(self, engine):
        """Premium below RM 50,000 should be allowed."""
        result = engine.evaluate("quote.calculate", {"premium": 30000})
        assert result.effect.value == "allow"
        assert "high_premium_approval" not in result.matched_rules


# ══════════════════════════════════════════════════════════════════
# 6. Integration — Policy + Tool + Session (5 tests)
# ══════════════════════════════════════════════════════════════════


class TestPolicyIntegration:
    """Policy Engine integrated with ToolRegistry and Session."""

    @pytest.fixture
    def setup(self):
        from src.tools.registry import ToolRegistry
        from src.tools.insurance.quote_tools import (
            register_all_quote_tools, reset_shared_adapter,
        )
        from src.policy.engine import PolicyEngine, PolicyRule, PolicyEffect, PolicyCondition
        from src.runtime.session_runtime import SessionRuntime

        ToolRegistry.reset_instance()
        reset_shared_adapter()
        registry = ToolRegistry.get_instance()
        register_all_quote_tools(registry)

        policy = PolicyEngine()
        policy.add_rule(PolicyRule(
            name="block_submit_readonly",
            action="quote.submit",
            effect=PolicyEffect.DENY,
            reason="Submit is disabled in this environment.",
        ))
        policy.add_rule(PolicyRule(
            name="high_premium_approval",
            action="quote.calculate",
            effect=PolicyEffect.REQUIRE_APPROVAL,
            reason="Quotes over RM 50,000 require manager approval.",
            conditions=[PolicyCondition(field="premium", operator=">", value=50000)],
            metadata={"approver": "manager"},
        ))

        session = SessionRuntime()

        yield registry, policy, session

        ToolRegistry.reset_instance()
        reset_shared_adapter()

    @pytest.fixture
    def event_loop(self):
        import asyncio
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_policy_check_before_tool(self, setup, event_loop):
        """Check policy before executing a tool."""
        registry, policy, _ = setup

        # Policy should block quote submit
        result = policy.evaluate("quote.submit", {})
        assert result.is_blocked is True

        # But allow create_quote
        result = policy.evaluate("create_quote", {})
        assert result.is_allowed is True

    def test_policy_approval_chain(self, setup, event_loop):
        """Check, escalate if needed, then execute."""
        registry, policy, session = setup

        s = session.create_session(customer_id="C001", task="fire_quote")
        session.start(s.id)

        # Attempt high premium quote
        policy_result = policy.evaluate("quote.calculate", {"premium": 100000})
        assert policy_result.needs_approval is True

        # Log the need for approval in session
        session.log_action(s.id, "policy_check", {
            "action": "quote.calculate",
            "effect": "require_approval",
            "reason": policy_result.reason,
        })
        session.set_data(s.id, "needs_approval", True)

        # Simulate approval
        session.set_data(s.id, "approved_by", "manager")
        session.set_data(s.id, "approved_at", "2026-07-27T12:00:00")

        # Now execute (approved)
        result = event_loop.run_until_complete(
            registry.execute("calculate_quote",
                             proposer_name="Tiong",
                             risk_class="fire",
                             sum_insured=5000000)
        )
        assert result.success is True
        session.log_tool_call(s.id, "calculate_quote", {}, result={"premium": result.data["total_premium"]})

        # Verify session
        final = session.get_session(s.id)
        assert final.collected_data["approved_by"] == "manager"
        assert len(final.tool_calls) == 1

    def test_policy_blocks_and_logs(self, setup, event_loop):
        """Blocked action should be logged."""
        registry, policy, session = setup

        s = session.create_session(customer_id="C001", task="fire_quote")
        session.start(s.id)

        # Policy blocks submit
        result = policy.evaluate("quote.submit", {})
        assert result.is_blocked is True

        session.log_action(s.id, "policy_blocked", {
            "action": "quote.submit",
            "reason": result.reason,
        })
        session.complete(s.id)

        log = session.get_session(s.id).action_log
        assert log[0]["action"] == "policy_blocked"
        assert "Submit is disabled" in str(log[0]["details"])

    def test_policy_warns_but_allows(self, setup, event_loop):
        """Warning should not block execution."""
        from src.policy.engine import PolicyEngine, PolicyRule, PolicyEffect, PolicyCondition

        registry, _, session = setup

        # Create policy with warn only
        policy = PolicyEngine()
        policy.add_rule(PolicyRule(
            name="warn_discount",
            action="quote.calculate",
            effect=PolicyEffect.WARN,
            reason="Large discount requested.",
            conditions=[PolicyCondition(field="discount", operator=">", value=10)],
        ))

        result = policy.evaluate("quote.calculate", {"discount": 20})
        assert result.effect.value == "warn"
        assert len(result.warnings) > 0

    def test_multi_layer_policy_stack(self, setup, event_loop):
        """Multiple policies on same action — most restrictive wins."""
        from src.policy.engine import PolicyEngine, PolicyRule, PolicyEffect, PolicyCondition

        policy = PolicyEngine()
        policy.add_rules([
            PolicyRule(
                name="deny_fire_high_value",
                action="quote.calculate",
                effect=PolicyEffect.DENY,
                reason="Fire quotes over RM 5M require special approval.",
                conditions=[
                    PolicyCondition(field="risk_class", operator="in", value=["fire"]),
                    PolicyCondition(field="sum_insured", operator=">", value=5000000),
                ],
            ),
            PolicyRule(
                name="warn_high_value",
                action="quote.calculate",
                effect=PolicyEffect.WARN,
                reason="High value quote.",
                conditions=[PolicyCondition(field="sum_insured", operator=">", value=1000000)],
            ),
        ])

        # Under 1M — should pass
        r1 = policy.evaluate("quote.calculate", {"sum_insured": 500000, "risk_class": "fire"})
        assert r1.effect.value == "allow"

        # 1M-5M — should warn
        r2 = policy.evaluate("quote.calculate", {"sum_insured": 2000000, "risk_class": "fire"})
        assert r2.effect.value == "warn"

        # Over 5M fire — should deny (DENY > WARN)
        r3 = policy.evaluate("quote.calculate", {"sum_insured": 6000000, "risk_class": "fire"})
        assert r3.effect.value == "deny"
        assert r3.reason == "Fire quotes over RM 5M require special approval."
