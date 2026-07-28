"""Tests for Portal Validation Engine.

Covers:
- Data models (ValidationContext, ValidationResult, ValidationError, etc.)
- ValidationRuleRegistry (registration, resolution, portal mappings)
- ValidationEngine (validate, validate_or_raise, rule execution)
- ValidationLoader (YAML loading)
- Rules (RequiredFieldRule, AgeRule, ICRule, OccupationRule, PremiumRule, PortalValidationRule)
- PortalValidationAdapter (portal state collection)
- Integration (ExecutionEngine integration pattern)
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime

import pytest

from src.portal.validation.models import (
    RuleStatus,
    Severity,
    ValidationContext,
    ValidationError,
    ValidationResult,
    ValidationRule,
    ValidationWarning,
)
from src.portal.validation.engine import ValidationEngine
from src.portal.validation.registry import ValidationRuleRegistry
from src.portal.validation.loader import ValidationLoader
from src.portal.validation.adapters.portal_validation import (
    PortalValidationAdapter,
)
from src.portal.validation.exceptions import (
    RuleNotFoundError,
    ValidationFailedError,
    ValidationConfigError,
)
from src.portal.validation.rules.base import BaseRule, get_field_value
from src.portal.validation.rules.required_field import RequiredFieldRule
from src.portal.validation.rules.age import AgeRule
from src.portal.validation.rules.ic import ICRule
from src.portal.validation.rules.occupation import OccupationRule
from src.portal.validation.rules.premium import PremiumRule
from src.portal.validation.rules.portal import PortalValidationRule


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def registry() -> ValidationRuleRegistry:
    reg = ValidationRuleRegistry()
    reg.register_type("required_field", RequiredFieldRule)
    reg.register_type("age", AgeRule)
    reg.register_type("ic", ICRule)
    reg.register_type("occupation", OccupationRule)
    reg.register_type("premium", PremiumRule)
    reg.register_type("portal", PortalValidationRule)
    return reg


@pytest.fixture
def engine(registry: ValidationRuleRegistry) -> ValidationEngine:
    return ValidationEngine(registry)


@pytest.fixture
def sample_context() -> ValidationContext:
    return ValidationContext(
        portal="great_eastern",
        action="create_quote",
        customer={
            "name": "John Tan",
            "age": 35,
            "dob": "1990-06-15",
            "ic": "900615-01-1234",
            "occupation": "Engineer",
            "email": "john@example.com",
        },
        quote={
            "premium": 523.0,
            "quote_no": "GE12345",
        },
    )


# =============================================================================
# Data Models
# =============================================================================


class TestSeverity:
    def test_values(self):
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"


class TestValidationError:
    def test_to_dict(self):
        err = ValidationError(
            rule_id="age_check",
            field="customer.dob",
            message="Age exceeds limit",
            severity="error",
            category="business",
        )
        d = err.to_dict()
        assert d["rule_id"] == "age_check"
        assert d["message"] == "Age exceeds limit"


class TestValidationResult:
    def test_defaults(self):
        r = ValidationResult()
        assert r.passed is True
        assert r.errors == []
        assert r.warnings == []

    def test_add_error(self):
        r = ValidationResult()
        r.add_error(ValidationError(rule_id="r1", message="fail"))
        assert r.passed is False
        assert r.error_count == 1

    def test_add_warning(self):
        r = ValidationResult()
        r.add_warning(ValidationWarning(rule_id="r1", message="warn"))
        assert r.passed is True  # Warnings don't block
        assert r.warning_count == 1

    def test_merge(self):
        r1 = ValidationResult()
        r1.add_error(ValidationError(rule_id="r1", message="e1"))

        r2 = ValidationResult()
        r2.add_warning(ValidationWarning(rule_id="r2", message="w2"))

        r1.merge(r2)
        assert r1.error_count == 1
        assert r1.warning_count == 1
        assert r1.passed is False

    def test_to_dict(self):
        r = ValidationResult()
        r.add_error(ValidationError(rule_id="r1", message="fail"))
        d = r.to_dict()
        assert d["passed"] is False
        assert d["error_count"] == 1


class TestValidationContext:
    def test_get_customer_field(self, sample_context: ValidationContext):
        assert sample_context.get_customer_field("name") == "John Tan"
        assert sample_context.get_customer_field("age") == 35

    def test_get_quote_field(self, sample_context: ValidationContext):
        assert sample_context.get_quote_field("premium") == 523.0

    def test_get_nested(self):
        ctx = ValidationContext(
            customer={"address": {"city": "Kuala Lumpur", "state": "KL"}}
        )
        assert ctx.get_customer_field("address.city") == "Kuala Lumpur"

    def test_get_default(self, sample_context: ValidationContext):
        assert sample_context.get_customer_field("nonexistent", "N/A") == "N/A"


# =============================================================================
# ValidationRuleRegistry
# =============================================================================


class TestValidationRuleRegistry:
    def test_register_and_get_type(self, registry: ValidationRuleRegistry):
        assert registry.has_type("age")
        cls = registry.get_type("age")
        assert cls == AgeRule

    def test_get_type_not_found(self, registry: ValidationRuleRegistry):
        with pytest.raises(RuleNotFoundError):
            registry.get_type("nonexistent")

    def test_add_rule(self, registry: ValidationRuleRegistry):
        rule = AgeRule(id="age_test", min_age=18, max_age=65)
        registry.add_rule(rule)
        assert registry.get_rule("age_test") is rule

    def test_add_portal_rule(self, registry: ValidationRuleRegistry):
        rule = AgeRule(id="age_ge", min_age=18, max_age=65)
        registry.add_rule(rule)
        registry.add_portal_rule("great_eastern", "create_quote", "age_ge")
        rules = registry.get_rules(portal="great_eastern", action="create_quote")
        assert len(rules) == 1
        assert rules[0].id == "age_ge"

    def test_get_rules_wildcard(self, registry: ValidationRuleRegistry):
        rule = RequiredFieldRule(id="req_name", fields=["name"])
        registry.add_rule(rule)
        registry.add_portal_rule("great_eastern", "*", "req_name")
        rules = registry.get_rules(portal="great_eastern", action="anything")
        assert len(rules) == 1

    def test_get_all_rules(self, registry: ValidationRuleRegistry):
        rule1 = AgeRule(id="r1")
        rule2 = ICRule(id="r2")
        registry.add_rule(rule1)
        registry.add_rule(rule2)
        assert len(registry.get_all_rules()) == 2

    def test_remove_rule(self, registry: ValidationRuleRegistry):
        rule = AgeRule(id="r1")
        registry.add_rule(rule)
        registry.add_portal_rule("ge", "create_quote", "r1")
        registry.remove_rule("r1")
        assert registry.get_rule("r1") is None
        assert len(registry.get_rules(portal="ge", action="create_quote")) == 0

    def test_list_types(self, registry: ValidationRuleRegistry):
        types = registry.list_types()
        assert "age" in types
        assert "ic" in types

    def test_clear(self, registry: ValidationRuleRegistry):
        registry.add_rule(AgeRule(id="r1"))
        registry.clear()
        assert len(registry.get_all_rules()) == 0


# =============================================================================
# ValidationEngine
# =============================================================================


@dataclass
class SimplePassRule(BaseRule):
    def validate(self, context: ValidationContext) -> RuleStatus:
        return self.pass_()


@dataclass
class SimpleFailRule(BaseRule):
    def validate(self, context: ValidationContext) -> RuleStatus:
        return self.fail()


@dataclass
class SkipRule(BaseRule):
    enabled: bool = False

    def validate(self, context: ValidationContext) -> RuleStatus:
        return self.fail()  # Should never be called


@dataclass
class ErrorRule(BaseRule):
    def validate(self, context: ValidationContext) -> RuleStatus:
        raise RuntimeError("Internal failure")


class TestValidationEngine:
    def test_validate_passes(self, engine: ValidationEngine):
        registry = engine.get_registry()
        registry.add_rule(SimplePassRule(id="pass"))
        result = engine.validate_rules(
            ValidationContext(), [SimplePassRule(id="pass")]
        )
        assert result.passed is True

    def test_validate_fails(self, engine: ValidationEngine):
        result = engine.validate_rules(
            ValidationContext(), [SimpleFailRule(id="fail")]
        )
        assert result.passed is False
        assert result.error_count == 1

    def test_validate_skips_disabled(self, engine: ValidationEngine):
        result = engine.validate_rules(
            ValidationContext(), [SkipRule(id="skip")]
        )
        assert result.passed is True  # No rules actually ran
        assert len(result.executed_rules) == 1
        assert "skipped" in result.executed_rules[0]

    def test_validate_handles_rule_error(self, engine: ValidationEngine):
        result = engine.validate_rules(
            ValidationContext(), [ErrorRule(id="err")]
        )
        # Rule execution errors are caught and added as validation errors
        assert result.passed is False
        assert any("Internal failure" in e.message for e in result.errors)

    def test_validate_or_raise(self, engine: ValidationEngine):
        with pytest.raises(ValidationFailedError):
            engine.validate_or_raise(
                ValidationContext(),
                rules=[SimpleFailRule(id="fail")],
            )

    def test_validate_or_raise_passes(self, engine: ValidationEngine):
        result = engine.validate_or_raise(
            ValidationContext(),
            rules=[SimplePassRule(id="pass")],
        )
        assert result.passed is True

    def test_validate_with_portal_filter(
        self, registry: ValidationRuleRegistry, engine: ValidationEngine
    ):
        rule = SimpleFailRule(id="ge_rule")
        registry.add_rule(rule)
        registry.add_portal_rule("great_eastern", "create_quote", "ge_rule")

        result = engine.validate(
            ValidationContext(portal="great_eastern", action="create_quote"),
            portal="great_eastern",
            action="create_quote",
        )
        assert result.passed is False

    def test_validate_no_rules(self, engine: ValidationEngine):
        result = engine.validate(
            ValidationContext(), portal="unknown", action="unknown"
        )
        assert result.passed is True  # No rules = pass


# =============================================================================
# RequiredFieldRule
# =============================================================================


class TestRequiredFieldRule:
    def test_field_present(self):
        rule = RequiredFieldRule(id="req_name", fields=["customer.name"])
        ctx = ValidationContext(customer={"name": "John"})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_field_missing(self):
        rule = RequiredFieldRule(id="req_name", fields=["customer.name"])
        ctx = ValidationContext(customer={})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_field_empty(self):
        rule = RequiredFieldRule(id="req_name", fields=["customer.name"])
        ctx = ValidationContext(customer={"name": ""})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_field_empty_allowed(self):
        rule = RequiredFieldRule(id="req_name", fields=["customer.name"],
                                  allow_empty=True)
        ctx = ValidationContext(customer={"name": ""})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_single_field_attr(self):
        rule = RequiredFieldRule(id="req_email", field="customer.email")
        ctx = ValidationContext(customer={"email": "a@b.com"})
        assert rule.validate(ctx) == RuleStatus.PASSED


# =============================================================================
# AgeRule
# =============================================================================


class TestAgeRule:
    def test_age_in_range(self):
        rule = AgeRule(id="age_check", min_age=18, max_age=65,
                       field="customer.age")
        ctx = ValidationContext(customer={"age": 35})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_age_too_young(self):
        rule = AgeRule(id="age_check", min_age=18, max_age=65,
                       field="customer.age")
        ctx = ValidationContext(customer={"age": 15})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_age_too_old(self):
        rule = AgeRule(id="age_check", min_age=18, max_age=65,
                       field="customer.age")
        ctx = ValidationContext(customer={"age": 70})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_age_from_dob(self):
        rule = AgeRule(id="age_check", min_age=18, max_age=65,
                       field="customer.dob")
        # DOB 1990 would make them ~36
        ctx = ValidationContext(customer={"dob": "1990-06-15"})
        status = rule.validate(ctx)
        # May pass or fail depending on current year, but should not error
        assert status in (RuleStatus.PASSED, RuleStatus.FAILED)

    def test_age_missing(self):
        rule = AgeRule(id="age_check", min_age=18, max_age=65,
                       field="customer.age")
        ctx = ValidationContext(customer={})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_age_invalid(self):
        rule = AgeRule(id="age_check", min_age=18, max_age=65,
                       field="customer.age")
        ctx = ValidationContext(customer={"age": "invalid"})
        assert rule.validate(ctx) == RuleStatus.ERROR


# =============================================================================
# ICRule
# =============================================================================


class TestICRule:
    def test_valid_my_ic(self):
        rule = ICRule(id="ic_check", field="customer.ic", country="MY")
        ctx = ValidationContext(customer={"ic": "900615-01-1234"})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_valid_ic_no_dash(self):
        rule = ICRule(id="ic_check", field="customer.ic")
        ctx = ValidationContext(customer={"ic": "900615011234"})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_invalid_ic_too_short(self):
        rule = ICRule(id="ic_check", field="customer.ic")
        ctx = ValidationContext(customer={"ic": "12345"})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_invalid_ic_wrong_format(self):
        rule = ICRule(id="ic_check", field="customer.ic")
        ctx = ValidationContext(customer={"ic": "not-an-ic"})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_ic_missing(self):
        rule = ICRule(id="ic_check", field="customer.ic")
        ctx = ValidationContext(customer={})
        assert rule.validate(ctx) == RuleStatus.FAILED


# =============================================================================
# OccupationRule
# =============================================================================


class TestOccupationRule:
    def test_allowed_occupation(self):
        rule = OccupationRule(id="occ_check", allowed=["Engineer", "Doctor"],
                              field="customer.occupation")
        ctx = ValidationContext(customer={"occupation": "Engineer"})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_blocked_occupation(self):
        rule = OccupationRule(id="occ_check", blocked=["Pilot", "Diver"],
                              field="customer.occupation")
        ctx = ValidationContext(customer={"occupation": "Pilot"})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_not_in_allowed(self):
        rule = OccupationRule(id="occ_check", allowed=["Engineer", "Doctor"],
                              field="customer.occupation")
        ctx = ValidationContext(customer={"occupation": "Chef"})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_empty_allowed_and_blocked(self):
        rule = OccupationRule(id="occ_check", field="customer.occupation")
        ctx = ValidationContext(customer={"occupation": "AnyJob"})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_case_insensitive(self):
        rule = OccupationRule(id="occ_check", allowed=["engineer"],
                              field="customer.occupation")
        ctx = ValidationContext(customer={"occupation": "Engineer"})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_occupation_missing(self):
        rule = OccupationRule(id="occ_check", field="customer.occupation")
        ctx = ValidationContext(customer={})
        assert rule.validate(ctx) == RuleStatus.FAILED


# =============================================================================
# PremiumRule
# =============================================================================


class TestPremiumRule:
    def test_premium_within_limit(self):
        rule = PremiumRule(id="prem_check", max_premium=10000,
                           field="quote.premium")
        ctx = ValidationContext(quote={"premium": 523.0})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_premium_exceeds_limit(self):
        rule = PremiumRule(id="prem_check", max_premium=500,
                           field="quote.premium")
        ctx = ValidationContext(quote={"premium": 523.0})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_premium_below_min(self):
        rule = PremiumRule(id="prem_check", min_premium=100,
                           field="quote.premium")
        ctx = ValidationContext(quote={"premium": 50.0})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_premium_no_limit(self):
        rule = PremiumRule(id="prem_check", field="quote.premium")
        ctx = ValidationContext(quote={"premium": 999999.0})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_premium_missing(self):
        rule = PremiumRule(id="prem_check", field="quote.premium")
        ctx = ValidationContext(quote={})
        assert rule.validate(ctx) == RuleStatus.FAILED


# =============================================================================
# PortalValidationRule
# =============================================================================


class TestPortalValidationRule:
    def test_no_portal_errors(self):
        rule = PortalValidationRule(id="portal_check")
        ctx = ValidationContext(portal_state={"errors": []})
        assert rule.validate(ctx) == RuleStatus.PASSED

    def test_portal_errors_present(self):
        rule = PortalValidationRule(id="portal_check")
        ctx = ValidationContext(
            portal_state={"errors": ["Medical question required"]}
        )
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_portal_check_expected_value(self):
        rule = PortalValidationRule(
            id="portal_check", check="submit_enabled", expected=True
        )
        ctx = ValidationContext(portal_state={"submit_enabled": False})
        assert rule.validate(ctx) == RuleStatus.FAILED

    def test_portal_check_passes(self):
        rule = PortalValidationRule(
            id="portal_check", check="submit_enabled", expected=True
        )
        ctx = ValidationContext(portal_state={"submit_enabled": True})
        assert rule.validate(ctx) == RuleStatus.PASSED


# =============================================================================
# PortalValidationAdapter
# =============================================================================


class TestPortalValidationAdapter:
    def test_collect_empty_state(self):
        adapter = PortalValidationAdapter()
        state = adapter.collect_portal_state("great_eastern")
        assert "errors" in state
        assert "session_valid" in state

    def test_create_context(self):
        adapter = PortalValidationAdapter()
        ctx = adapter.create_context(
            portal="great_eastern",
            action="create_quote",
            customer={"name": "John"},
            quote={"premium": 500},
        )
        assert ctx.portal == "great_eastern"
        assert ctx.customer["name"] == "John"
        assert ctx.quote["premium"] == 500
        assert "errors" in ctx.portal_state

    def test_great_eastern_medical_question(self):
        adapter = PortalValidationAdapter()
        state = adapter.collect_portal_state(
            "great_eastern",
            {"error_text": "Medical Question Required"},
        )
        assert state.get("medical_question_required") is True

    def test_session_expired(self):
        adapter = PortalValidationAdapter()
        state = adapter.collect_portal_state(
            "great_eastern",
            {"error_text": "Your session has expired"},
        )
        assert state.get("session_valid") is False

    def test_aia_declaration(self):
        adapter = PortalValidationAdapter()
        state = adapter.collect_portal_state(
            "aia",
            {"error_text": "Declaration is required"},
        )
        assert state.get("declaration_required") is True


# =============================================================================
# ValidationLoader (YAML)
# =============================================================================


class TestValidationLoader:
    @pytest.fixture
    def yaml_file(self):
        content = """
portal: great_eastern
validation:
  create_quote:
    rules:
      - id: age_limit
        type: age
        severity: ERROR
        min: 18
        max: 65
        field: customer.age
      - id: ic_check
        type: ic
        severity: ERROR
        field: customer.ic
      - id: premium_check
        type: premium
        severity: WARNING
        max: 10000
        field: quote.premium
  renew_policy:
    rules:
      - id: required_policy_no
        type: required_field
        severity: ERROR
        fields: ["quote.policy_no"]
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(content)
            path = f.name
        yield path
        os.unlink(path)

    def test_load_file(self, registry: ValidationRuleRegistry, yaml_file: str):
        loader = ValidationLoader(registry)
        count = loader.load_file(yaml_file)
        assert count == 4  # 3 from create_quote + 1 from renew_policy

    def test_loaded_rules_registered(self, registry: ValidationRuleRegistry, yaml_file: str):
        loader = ValidationLoader(registry)
        loader.load_file(yaml_file)
        assert registry.get_rule("age_limit") is not None
        assert registry.get_rule("ic_check") is not None

    def test_portal_mapping(self, registry: ValidationRuleRegistry, yaml_file: str):
        loader = ValidationLoader(registry)
        loader.load_file(yaml_file)
        rules = registry.get_rules(portal="great_eastern", action="create_quote")
        assert len(rules) == 3

    def test_load_nonexistent(self, registry: ValidationRuleRegistry):
        loader = ValidationLoader(registry)
        with pytest.raises(ValidationConfigError):
            loader.load_file("/nonexistent/path.yaml")

    def test_load_directory(self, registry: ValidationRuleRegistry, yaml_file: str):
        directory = os.path.dirname(yaml_file)
        loader = ValidationLoader(registry)
        count = loader.load_directory(directory)
        assert count >= 4

    def test_loaded_files_tracking(self, registry: ValidationRuleRegistry, yaml_file: str):
        loader = ValidationLoader(registry)
        loader.load_file(yaml_file)
        assert len(loader.loaded_files()) == 1
        assert yaml_file in loader.loaded_files()[0]


# =============================================================================
# Integration — ExecutionEngine + ValidationEngine
# =============================================================================


class TestValidationIntegration:
    def test_validation_in_execution_step(self, registry: ValidationRuleRegistry):
        """Simulate how ValidationEngine integrates with ExecutionEngine."""
        engine = ValidationEngine(registry)

        # Register business rules
        age_rule = AgeRule(
            id="age_check", min_age=18, max_age=65,
            field="customer.age", severity="error",
        )
        registry.add_rule(age_rule)
        registry.add_portal_rule("great_eastern", "create_quote", "age_check")

        # Scenario: valid customer
        ctx = ValidationContext(
            portal="great_eastern",
            action="create_quote",
            customer={"age": 35},
        )
        result = engine.validate(
            ctx, portal="great_eastern", action="create_quote",
        )
        assert result.passed is True

        # Scenario: invalid age
        ctx2 = ValidationContext(
            portal="great_eastern",
            action="create_quote",
            customer={"age": 17},
        )
        result2 = engine.validate(
            ctx2, portal="great_eastern", action="create_quote",
        )
        assert result2.passed is False

    def test_full_validation_pipeline(self, registry: ValidationRuleRegistry):
        """End-to-end: multiple rules running on a single context."""
        engine = ValidationEngine(registry)

        # Register all rules
        registry.add_rule(AgeRule(id="age", min_age=18, max_age=65,
                                   field="customer.age"))
        registry.add_rule(ICRule(id="ic", field="customer.ic"))
        registry.add_rule(OccupationRule(id="occ", allowed=["Engineer"],
                                          field="customer.occupation"))
        registry.add_rule(PremiumRule(id="prem", max_premium=10000,
                                       field="quote.premium"))

        ctx = ValidationContext(
            customer={
                "age": 35,
                "ic": "900615-01-1234",
                "occupation": "Engineer",
            },
            quote={"premium": 523.0},
        )
        result = engine.validate_rules(ctx, registry.get_all_rules())
        assert result.passed is True

        # Now test with bad data
        ctx2 = ValidationContext(
            customer={
                "age": 17,
                "ic": "invalid",
                "occupation": "Pilot",
            },
            quote={"premium": 99999.0},
        )
        result2 = engine.validate_rules(ctx2, registry.get_all_rules())
        assert result2.passed is False
        assert result2.error_count == 4  # All 4 rules fail
