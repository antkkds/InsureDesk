"""Comparison tests: FormSpec-driven execution == existing FillEngine path.

Phase 3 vertical slice validation (ChatGPT review step 5):
the same business data filled through the NEW FormSpec path must produce
the same field results as the EXISTING direct FillEngine path, on the
same mock browser state.

This proves the FormSpec layer is a pure abstraction (no behavior drift)
before we point it at the real GEARS browser.
"""
from __future__ import annotations

import os

import pytest

from src.fill.engine import FillEngine
from src.fill.schema import FillSchema, FieldDefinition, FieldType
from src.portal.formspec import MotorPrivateCarSpec
from tests.mock_browser import MockBrowser
from tests.test_autocomplete_strategy import MockAutocompleteBrowser

FORMS_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "portal", "forms")
MOTOR_YAML = os.path.join(FORMS_DIR, "motor_private_car.yaml")

# Sample business data for a private car quote (same shape used in production)
# NOTE: field names follow the LIVE-CAPTURED YAML v2 structure
# (owner/address/vehicle/drivers). Auto-populated fields (dob, nationality,
# chassis, engine, make, model, marketValue...) are intentionally OMITTED —
# the portal fills them from NRIC/vehicle lookup.
SAMPLE_DATA = {
    # quotation_details (confirmed selectors)
    "applicant_type": "individual",
    "condition": "REGISTERED",
    "id_type": "NRIC",
    "id_number": "881212145678",
    "sst_number": None,          # optional
    "vehicle_number": "wqk 1234",
    "place": "KUALA LUMPUR",
    # owner
    "salutation": "Mr",
    "fullname": "Fionn Liang",
    "gender": "M",               # radio values are M/F (NOT Male/Female)
    "marital_status": "Single",
    "years_driving_exp": "5",
    "mobile": "0123456789",
    "home_phone": None,
    "email": "fionn@example.com",
    "pds_consent": True,
    # address
    "postcode": "50000",
    "state": "KUALA LUMPUR",
    "address1": "12, Jalan Merdeka",
    "address2": "Taman Desa",
    # vehicle
    "body_type": "SEDAN",
    "seating_capacity": "5",
    "safety_feature": "ABS & Airbags (more than 2)",
    "hire_purchase": "N",        # radio values are Y/N (btn_0/btn_1)
    # drivers
    "all_drivers_cover": False,
    # sum_insured (step 3)
    "intermediary_decl_1": True,
    "intermediary_decl_2": True,
}


def _register_form_fields(browser: MockBrowser, schema: FillSchema) -> None:
    """Register all selectors of a schema as present on the mock page."""
    for fd in schema.fields.values():
        browser.register_selector(fd.selector, found=True, visible=True)
        if fd.type == FieldType.CHECKBOX:
            browser.register_checkbox(fd.selector, False)
        elif fd.type == FieldType.RADIO:
            # Radio strategy resolves value → selector[value="X"] (list form)
            # or explicit selector map (dict form). Register both the base
            # selector and the value-suffixed variant so is_checked works.
            values = fd.options.get("values", [])
            if isinstance(values, list):
                for v in values:
                    browser.register_selector(
                        f'{fd.selector}[value="{v}"]', found=True, visible=True
                    )
                    browser.register_checkbox(
                        f'{fd.selector}[value="{v}"]', False
                    )
            elif isinstance(values, dict):
                for sel in values.values():
                    browser.register_selector(sel, found=True, visible=True)
                    browser.register_checkbox(sel, False)
        elif fd.type == FieldType.TEXT and fd.options.get("autocomplete"):
            # Simulate Angular mat-option panel for autocomplete fields
            if hasattr(browser, "register_options"):
                name = fd.name
                if name in ("salutation",):
                    browser.register_options(fd.selector, ["Mr", "Ms", "Madam"])
                elif name == "marital_status":
                    browser.register_options(fd.selector, ["Married", "Single"])
                elif name in ("nationality", "country"):
                    browser.register_options(fd.selector, ["Malaysia", "Singapore"])
                elif name == "state":
                    browser.register_options(fd.selector, ["KUALA LUMPUR", "SELANGOR"])
                elif name == "place":
                    browser.register_options(fd.selector, ["KUALA LUMPUR", "SELANGOR"])
                elif name == "body_type":
                    browser.register_options(fd.selector, ["SEDAN", "SALOON", "SUV"])
                elif name == "safety_feature":
                    browser.register_options(fd.selector, ["ABS & Airbags (more than 2)", "ABS (No Airbags)"])
                elif name == "make":
                    browser.register_options(fd.selector, ["Toyota", "Honda", "Perodua"])
                elif name == "model":
                    browser.register_options(fd.selector, ["Vios", "City", "Myvi"])
                elif "REGISTERED" in fd.options.get("hint", ""):
                    browser.register_options(fd.selector, ["NEW REGISTERED", "REGISTERED"])
                elif "NRIC" in fd.options.get("hint", ""):
                    browser.register_options(fd.selector, ["NRIC", "Passport"])
                else:
                    browser.register_options(fd.selector, ["Kuala Lumpur", "Selangor"])


class TestFormSpecParity:
    """FormSpec path must equal direct FillEngine path on same state."""

    @pytest.mark.asyncio
    async def test_quotation_details_parity(self):
        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
        engine = FillEngine()

        # --- Path A: FormSpec-driven ---
        schema_a = spec.section("quotation_details").to_fill_schema()
        browser_a = MockAutocompleteBrowser()
        _register_form_fields(browser_a, schema_a)
        result_a = await engine.fill_section(browser_a, schema_a, SAMPLE_DATA)

        # --- Path B: existing direct usage (same schema shape) ---
        schema_b = FillSchema(
            name="quotation_details",
            fields={
                f.name: FieldDefinition(
                    name=f.name, selector=f.selector, type=FieldType(f.type),
                    required=f.required, verify=f.verify, retry=f.retry,
                    clear_first=f.clear_first, timeout=f.timeout,
                    transform=f.transform, format=f.format,
                    options=dict(f.options), max_length=f.max_length,
                )
                for f in spec.section("quotation_details").fields
            },
        )
        browser_b = MockAutocompleteBrowser()
        _register_form_fields(browser_b, schema_b)
        result_b = await engine.fill_section(browser_b, schema_b, SAMPLE_DATA)

        assert result_a.success is True
        assert result_b.success is True
        # Same counts, same field outcomes, same durations structure
        assert result_a.succeeded == result_b.succeeded
        assert result_a.failed == result_b.failed
        assert result_a.total_fields == result_b.total_fields
        assert [f.field for f in result_a.fields] == [f.field for f in result_b.fields]
        assert [f.success for f in result_a.fields] == [f.success for f in result_b.fields]

    @pytest.mark.asyncio
    async def test_all_sections_parity(self):
        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
        engine = FillEngine()

        for section in spec.sections:
            schema = section.to_fill_schema()
            browser = MockAutocompleteBrowser()
            _register_form_fields(browser, schema)
            result = await engine.fill_section(browser, schema, SAMPLE_DATA)
            assert result.success, (
                f"section '{section.name}' failed: "
                + "; ".join(f.error or "" for f in result.fields if not f.success)
            )

    @pytest.mark.asyncio
    async def test_optional_fields_skipped_not_failed(self):
        """Optional fields with no data must be skipped (existing behavior)."""
        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
        engine = FillEngine()
        schema = spec.section("quotation_details").to_fill_schema()
        browser = MockAutocompleteBrowser()
        _register_form_fields(browser, schema)

        data = dict(SAMPLE_DATA)
        data["sst_number"] = None  # optional, no value
        result = await engine.fill_section(browser, schema, data)

        # sst_number must be skipped, not failed
        sst = next(f for f in result.fields if f.field == "sst_number")
        assert sst.success is True
        assert "Skipped" in (sst.message or "")

    @pytest.mark.asyncio
    async def test_required_missing_fails_cleanly(self):
        """Missing required field → section failure with field-level error."""
        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
        engine = FillEngine()
        schema = spec.section("quotation_details").to_fill_schema()
        browser = MockAutocompleteBrowser()
        _register_form_fields(browser, schema)

        data = dict(SAMPLE_DATA)
        data["id_number"] = None  # required!
        result = await engine.fill_section(browser, schema, data)

        assert result.success is False
        id_field = next(f for f in result.fields if f.field == "id_number")
        assert id_field.success is False
        assert "Required field" in (id_field.error or "")

    @pytest.mark.asyncio
    async def test_uppercase_transform_applied(self):
        """vehicle_number has transform: uppercase — value must be normalized."""
        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
        engine = FillEngine()
        schema = spec.section("quotation_details").to_fill_schema()
        browser = MockAutocompleteBrowser()
        _register_form_fields(browser, schema)

        data = dict(SAMPLE_DATA)
        data["vehicle_number"] = "wqk 1234"  # lowercase input
        result = await engine.fill_section(browser, schema, data)

        assert result.success is True
        filled = browser.filled.get("#vehicleNumber")
        assert filled == "WQK 1234"
