"""Tests for InsureDesk Quote Tools (Phase 3 + 4A)."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import pytest

from src.tools import ToolRegistry, ToolExecutionResult, register_all_tools
from src.tools.quote import CalculateQuoteTool, QuoteRequest, QuoteResult, ValidationResult, ValidationError, QuoteValidator
from src.portal.quote_executor import (
    QuoteExecutor,
    _parse_premium,
    _parse_breakdown,
    _ok,
    _error,
)
from src.portal.mapping import (
    load_portal_mapping,
    get_selector,
    get_field_def,
    list_available_portals,
)


# ══════════════════════════════════════════════════════════════════
# QuoteRequest / QuoteResult Tests
# ══════════════════════════════════════════════════════════════════


class TestQuoteRequest:
    def test_defaults(self):
        r = QuoteRequest()
        assert r.portal == ""
        assert r.product == ""
        assert r.customer == {}
        assert r.risk == {}
        assert r.coverage == {}

    def test_from_dict(self):
        r = QuoteRequest.from_dict({
            "portal": "great_eastern",
            "product": "IFE",
            "customer": {"name": "Alice"},
            "risk": {"sum_insured": 500000},
        })
        assert r.portal == "great_eastern"
        assert r.product == "IFE"
        assert r.customer["name"] == "Alice"
        assert r.risk["sum_insured"] == 500000

    def test_to_dict(self):
        r = QuoteRequest(portal="ge", product="EQ")
        d = r.to_dict()
        assert d["portal"] == "ge"
        assert d["product"] == "EQ"


class TestQuoteResult:
    def test_ok(self):
        r = QuoteResult.ok(premium=1234.50)
        assert r.success
        assert r.premium == 1234.50
        assert r.currency == "MYR"

    def test_ok_with_breakdown(self):
        r = QuoteResult.ok(
            premium=1500.00,
            breakdown={"base": 1200, "loading": 300},
            details="RM 1,500.00",
        )
        assert r.success
        assert r.premium == 1500.00
        assert r.breakdown["base"] == 1200

    def test_fail(self):
        r = QuoteResult.fail("Portal timeout", error_code="timeout")
        assert not r.success
        assert r.error == "Portal timeout"
        assert r.error_code == "timeout"

    def test_to_dict(self):
        r = QuoteResult.ok(premium=999.99)
        d = r.to_dict()
        assert d["success"] is True
        assert d["premium"] == 999.99


# ══════════════════════════════════════════════════════════════════
# QuoteExecutor dict-based helpers Tests
# ══════════════════════════════════════════════════════════════════


class TestQuoteExecutorHelpers:
    def test_ok_result(self):
        r = _ok(1234.50)
        assert r["success"] is True
        assert r["premium"] == 1234.50

    def test_ok_with_breakdown(self):
        r = _ok(1500.00, breakdown={"base": 1200}, details="RM 1,500")
        assert r["success"] is True
        assert r["breakdown"]["base"] == 1200

    def test_error_result(self):
        r = _error("Something went wrong", "timeout")
        assert r["success"] is False
        assert r["error"] == "Something went wrong"
        assert r["error_code"] == "timeout"
        assert r["premium"] == 0.0


# ══════════════════════════════════════════════════════════════════
# Premium Parsing Tests
# ══════════════════════════════════════════════════════════════════


class TestPremiumParsing:
    def test_rm_format(self):
        assert _parse_premium("RM 1,234.56") == 1234.56
        assert _parse_premium("RM 1000") == 1000.0
        assert _parse_premium("RM500") == 500.0

    def test_myr_format(self):
        assert _parse_premium("MYR 2,500.00") == 2500.0

    def test_numeric_format(self):
        assert _parse_premium("1234.56") == 1234.56
        assert _parse_premium("1,234.56") == 1234.56

    def test_empty_or_invalid(self):
        assert _parse_premium("") == 0.0
        assert _parse_premium("Calculating...") == 0.0
        assert _parse_premium(None) == 0.0

    def test_breakdown_parsing(self):
        text = "Base Premium: RM 1,200.00\nLoading: RM 300.00\nTotal: RM 1,500.00"
        bd = _parse_breakdown(text)
        assert "Base Premium" in bd
        assert bd["Base Premium"] == 1200.00
        assert "Loading" in bd
        assert bd["Loading"] == 300.00

    def test_breakdown_empty(self):
        assert _parse_breakdown("") == {}
        assert _parse_breakdown(None) == {}


# ══════════════════════════════════════════════════════════════════
# YAML Portal Mapping Tests (Phase 4A)
# ══════════════════════════════════════════════════════════════════


class TestYamlMapping:
    """Test the expanded YAML quotation schema."""

    @pytest.fixture
    def ge(self):
        return load_portal_mapping("great_eastern")

    def test_load_ge(self, ge):
        assert ge is not None
        assert ge.name == "Great Eastern"

    def test_old_string_selector_still_works(self, ge):
        """Old-style string selectors must still resolve."""
        s = get_selector(ge, "login", "username")
        assert s == "input[name='oac_username']"

        s = get_selector(ge, "login", "submit")
        assert s is not None

    def test_new_dict_selector(self, ge):
        """New-style dict selectors with 'selector' key."""
        s = get_selector(ge, "quotation", "product_select")
        assert s == "#productSelect"

    def test_nested_field_selector(self, ge):
        """Deep path to quotation.fields.<name>."""
        s = get_selector(ge, "quotation", "fields", "occupancy")
        assert s == "select[name='occupancy']"

    def test_get_field_def(self, ge):
        fd = get_field_def(ge, "sum_insured_building")
        assert fd is not None
        assert fd["type"] == "number"
        assert fd["required"] is True
        assert "selector" in fd

        fd2 = get_field_def(ge, "nonexistent")
        assert fd2 is None

    def test_field_def_required_flag(self, ge):
        fd = get_field_def(ge, "sum_insured_building")
        assert fd["required"] is True

        fd2 = get_field_def(ge, "property_postcode")
        assert "required" not in fd2 or not fd2["required"]

    def test_action_selectors(self, ge):
        actions = ge.selectors.get("quotation", {}).get("actions", {})
        assert actions is not None
        calc = actions.get("calculate", {})
        assert calc.get("selector") is not None
        assert calc.get("wait_after_ms", 0) > 0

    def test_output_selectors(self, ge):
        outputs = ge.selectors.get("quotation", {}).get("outputs", {})
        assert outputs is not None
        assert outputs["premium"]["selector"] == ".quoted-premium"

    def test_read_only_safety(self, ge):
        ro = ge.selectors.get("quotation", {}).get("read_only", {})
        assert ro is not None
        assert "issue_button" in ro
        assert "submit_button" in ro
        assert "pay_button" in ro

    def test_old_yaml_compatibility(self):
        """AIA and Allianz YAMLs (old format) must still load."""
        aia = load_portal_mapping("aia")
        assert aia is not None
        s = get_selector(aia, "login", "username")
        assert s is not None

        allianz = load_portal_mapping("allianz")
        assert allianz is not None
        s = get_selector(allianz, "login", "username")
        assert s is not None

    def test_list_portals(self):
        portals = list_available_portals()
        names = [p["name"] for p in portals]
        assert "Great Eastern" in names
        assert "Allianz Malaysia" in names
        assert "AIA Malaysia" in names


# ══════════════════════════════════════════════════════════════════
# CalculateQuoteTool Tests
# ══════════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════════
# QuoteValidator Tests (Phase 4B)
# ══════════════════════════════════════════════════════════════════


class TestQuoteValidator:
    """Test the quote validation layer."""

    @pytest.fixture
    def validator(self):
        return QuoteValidator()

    def test_ok_validation(self, validator):
        """Fully valid request passes."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": 500000,
                "property_address": "123 Jalan SS2",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert r.valid
        assert len(r.errors) == 0

    def test_missing_portal(self, validator):
        r = validator.validate({"product": "IFE"})
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "missing_required" in codes
        fields = [e.field for e in r.errors]
        assert "portal" in fields

    def test_missing_product(self, validator):
        r = validator.validate({"portal": "great_eastern"})
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "missing_required" in codes
        fields = [e.field for e in r.errors]
        assert "product" in fields

    def test_unknown_portal(self, validator):
        r = validator.validate({"portal": "nonexistent", "product": "IFE"})
        assert not r.valid
        assert r.errors[0].code == "unknown_portal"

    def test_missing_required_field_sum_insured(self, validator):
        """Required YAML field missing."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"occupancy": "Owner", "property_address": "123 Jalan"},
            "coverage": {"coverage_start": "2026-01-01",
                         "coverage_end": "2027-01-01"},
        })
        assert not r.valid
        yaml_fields = [e.yaml_field for e in r.errors]
        assert "sum_insured_building" in yaml_fields

    def test_missing_required_field_occupancy(self, validator):
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000, "property_address": "123"},
            "coverage": {"coverage_start": "2026-01-01",
                         "coverage_end": "2027-01-01"},
        })
        assert not r.valid
        yaml_fields = [e.yaml_field for e in r.errors]
        assert "occupancy" in yaml_fields

    def test_missing_required_field_coverage_start(self, validator):
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000, "occupancy": "Owner",
                     "property_address": "123 Jalan"},
            "coverage": {"coverage_end": "2027-01-01"},
        })
        assert not r.valid
        yaml_fields = [e.yaml_field for e in r.errors]
        assert "coverage_start" in yaml_fields
        assert "coverage_end" not in yaml_fields  # coverage_end is NOT required

    def test_missing_required_field_coverage_end(self, validator):
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000, "occupancy": "Owner",
                     "property_address": "123 Jalan"},
            "coverage": {"coverage_start": "2026-01-01"},
        })
        assert not r.valid
        yaml_fields = [e.yaml_field for e in r.errors]
        # coverage_end IS required in YAML
        assert "coverage_end" in yaml_fields

    def test_optional_fields_accepted(self, validator):
        """Optional fields with data are fine."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": 500000,
                "property_address": "123 Jalan",
                "property_postcode": "50200",
                "property_city": "KL",
                "occupancy": "Owner",
                "construction_type": "Brick",
                "year_built": 2010,
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert r.valid

    def test_number_type_error_string(self, validator):
        """String that's not a number for a number field."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": "not-a-number",
                "property_address": "123",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "type_error" in codes

    def test_number_type_error_boolean(self, validator):
        """Boolean for number field."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": True,
                "property_address": "123",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "type_error" in codes

    def test_number_type_valid_string(self, validator):
        """String containing a valid number is accepted."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": "500000",
                "property_address": "123 Jalan",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert r.valid

    def test_number_valid_float(self, validator):
        """Float is valid for number field."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": 500000.50,
                "property_address": "123 Jalan",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert r.valid

    def test_date_format_yyyymmdd(self, validator):
        """YYYY-MM-DD format accepted."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000, "property_address": "123",
                     "occupancy": "Owner"},
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert r.valid

    def test_date_format_ddmmyyyy(self, validator):
        """DD/MM/YYYY format accepted."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000, "property_address": "123",
                     "occupancy": "Owner"},
            "coverage": {
                "coverage_start": "01/01/2026",
                "coverage_end": "01/01/2027",
            },
        })
        assert r.valid

    def test_date_format_invalid(self, validator):
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {"sum_insured": 500000, "property_address": "123",
                     "occupancy": "Owner"},
            "coverage": {
                "coverage_start": "not-a-date",
                "coverage_end": "2027-01-01",
            },
        })
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "type_error" in codes
        fields = [e.field for e in r.errors]
        assert "coverage_start" in fields

    def test_business_rule_sum_insured_positive(self, validator):
        """sum_insured must be > 0."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": -100,
                "property_address": "123",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "business_rule" in codes

    def test_business_rule_sum_insured_zero(self, validator):
        """sum_insured = 0 is a business rule error."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": 0,
                "property_address": "123",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "business_rule" in codes

    def test_business_rule_coverage_end_after_start(self, validator):
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": 500000,
                "property_address": "123",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2027-01-01",
                "coverage_end": "2026-01-01",
            },
        })
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "business_rule" in codes

    def test_business_rule_same_date(self, validator):
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "risk": {
                "sum_insured": 500000,
                "property_address": "123",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2026-01-01",
            },
        })
        assert not r.valid
        codes = [e.code for e in r.errors]
        assert "business_rule" in codes

    def test_customer_fields_in_risk(self, validator):
        """Customer name alone (no risk fields) triggers required warnings."""
        r = validator.validate({
            "portal": "great_eastern",
            "product": "IFE",
            "customer": {"name": "Alice Tan", "ic": "880101-01-1234"},
        })
        assert not r.valid
        yaml_fields = [e.yaml_field for e in r.errors]
        # Required fields still need to be in risk/coverage, not just customer
        assert "sum_insured_building" in yaml_fields
        assert "occupancy" in yaml_fields

    def test_product_not_in_config_warning(self, validator):
        r = validator.validate({
            "portal": "great_eastern",
            "product": "UNKNOWN_PRODUCT",
            "risk": {
                "sum_insured": 500000,
                "property_address": "123",
                "occupancy": "Owner",
            },
            "coverage": {
                "coverage_start": "2026-01-01",
                "coverage_end": "2027-01-01",
            },
        })
        assert r.valid  # Non-fatal
        assert len(r.warnings) > 0

    def test_validation_result_to_dict(self):
        vr = ValidationResult.ok()
        d = vr.to_dict()
        assert d["valid"] is True
        assert d["errors"] == []

        ve = ValidationError(field="test", message="err", code="x")
        vr2 = ValidationResult.fail([ve])
        d2 = vr2.to_dict()
        assert d2["valid"] is False
        assert len(d2["errors"]) == 1
        assert d2["errors"][0]["field"] == "test"


class TestCalculateQuoteTool:
    def test_tool_metadata(self):
        tool = CalculateQuoteTool()
        assert tool.name == "calculate_quote"
        assert "READ_ONLY" in tool.description

    def test_missing_portal(self):
        tool = CalculateQuoteTool()
        result = asyncio.run(tool.execute({"product": "IFE"}))
        assert not result.success
        assert result.error_code == "validation_error"
        assert "validation" in result.error_context

    def test_missing_product(self):
        tool = CalculateQuoteTool()
        result = asyncio.run(tool.execute({"portal": "great_eastern"}))
        assert not result.success
        assert result.error_code == "validation_error"
        assert "validation" in result.error_context

    def test_no_browser_available(self):
        tool = CalculateQuoteTool()
        result = asyncio.run(tool.execute({
            "portal": "great_eastern", "product": "IFE",
            "risk": {"sum_insured": 500000, "occupancy": "Owner",
                     "property_address": "123 Jalan Test"},
            "coverage": {"coverage_start": "2026-01-01",
                         "coverage_end": "2027-01-01"},
        }))
        assert not result.success
        # Should pass validation but fail with no_browser, not crash
        assert result.error is not None
        assert result.error_code != "validation_error"

    def test_execute_via_registry(self):
        registry = ToolRegistry()
        register_all_tools(registry)
        result = asyncio.run(registry.execute(
            "calculate_quote",
            {
                "portal": "great_eastern", "product": "IFE",
                "risk": {"sum_insured": 500000, "occupancy": "Owner",
                         "property_address": "123 Jalan Test"},
                "coverage": {"coverage_start": "2026-01-01",
                             "coverage_end": "2027-01-01"},
            },
        ))
        assert not result.success  # No real browser
        assert result.error is not None
        assert result.error_code != "validation_error"


# ══════════════════════════════════════════════════════════════════
# Registration Tests
# ══════════════════════════════════════════════════════════════════


class TestRegistration:
    def test_registered_in_defaults(self):
        registry = ToolRegistry()
        register_all_tools(registry)
        assert registry.has_tool("calculate_quote")
        assert registry.has_tool("capture_mode")
        assert registry.tool_count == 2
