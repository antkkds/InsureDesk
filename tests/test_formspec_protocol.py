"""Tests for PortalDriver Protocol, ActionResult, and Motor FormSpec.

Covers the Phase 3 vertical slice (ChatGPT review steps 2-4):
  - ActionResult structured diagnostics + trace
  - PortalDriver Protocol compatibility (FormEngine, MockBrowser)
  - MotorPrivateCarSpec YAML round-trip + FillSchema conversion
"""
from __future__ import annotations

import os

import pytest

from src.portal.action_result import ActionResult, TraceEvent
from src.portal.formspec import MotorPrivateCarSpec, FormFieldSpec, FormSectionSpec
from src.portal.protocol import PortalDriver
from src.fill.schema import FieldType, FillSchema
from src.portal.form_engine import FormEngine
from tests.mock_browser import MockBrowser

FORMS_DIR = os.path.join(os.path.dirname(__file__), "..", "src", "portal", "forms")
MOTOR_YAML = os.path.join(FORMS_DIR, "motor_private_car.yaml")


# ---------------------------------------------------------------------------
# ActionResult
# ---------------------------------------------------------------------------

class TestActionResult:
    def test_ok_factory(self):
        r = ActionResult.ok("fill", selector="#x", message="done", duration_ms=5)
        assert r.success is True
        assert r.action == "fill"
        assert r.selector == "#x"
        assert r.duration_ms == 5

    def test_fail_factory(self):
        r = ActionResult.fail("click", selector="#y", error="not found")
        assert r.success is False
        assert r.error == "not found"
        assert r.message == "not found"  # message defaults to error

    def test_trace_accumulation(self):
        r = ActionResult.ok("fill", selector="#condition")
        r.add_trace(TraceEvent("attempt", "#condition", "ok", 42))
        r.add_trace(TraceEvent("verify", "#condition", "ok", 5))
        assert len(r.trace) == 2
        assert r.trace[0].kind == "attempt"
        assert r.trace[1].status == "ok"

    def test_to_dict_roundtrip_fields(self):
        r = ActionResult.fail("wait_for", selector="#x", error="timeout")
        r.add_trace(TraceEvent("retry", "#x", "timeout", 3000))
        d = r.to_dict()
        assert d["action"] == "wait_for"
        assert d["success"] is False
        assert d["error"] == "timeout"
        assert d["trace"][0]["status"] == "timeout"
        assert d["trace"][0]["duration_ms"] == 3000

    def test_summary(self):
        r = ActionResult.ok("navigate", selector="/home")
        assert "navigate" in r.summary
        assert "ok" in r.summary


# ---------------------------------------------------------------------------
# PortalDriver Protocol
# ---------------------------------------------------------------------------

class TestPortalDriverProtocol:
    @pytest.mark.asyncio
    async def test_mock_browser_satisfies_protocol(self):
        """MockBrowser (test double) must be a valid PortalDriver."""
        assert isinstance(MockBrowser(), PortalDriver)

    def test_form_engine_satisfies_protocol(self):
        """FormEngine (primary driver) must be a valid PortalDriver."""
        engine = FormEngine()
        assert isinstance(engine, PortalDriver)

    @pytest.mark.asyncio
    async def test_protocol_methods_are_awaitable(self):
        """Every protocol method should be async (awaitable)."""
        import inspect
        for name in ("navigate", "fill_text", "select_option", "click",
                     "get_text", "wait_for_selector", "upload_file",
                     "screenshot", "evaluate"):
            method = getattr(PortalDriver, name)
            assert inspect.iscoroutinefunction(method), f"{name} must be async"


# ---------------------------------------------------------------------------
# MotorPrivateCarSpec — YAML loading & conversion
# ---------------------------------------------------------------------------

class TestMotorPrivateCarSpec:
    def setup_method(self):
        self.spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)

    def test_loads_product_metadata(self):
        assert self.spec.product_id == "PMOT"
        assert self.spec.portal == "great_eastern_gears"
        assert "Private Car" in self.spec.product_name

    def test_sections_order_and_count(self):
        names = [s.name for s in self.spec.sections]
        assert names == ["quotation_details", "owner", "address", "vehicle", "drivers"]

    def test_quotation_details_confirmed_selectors(self):
        sec = self.spec.section("quotation_details")
        assert sec is not None
        ids = [f.name for f in sec.fields]
        # Confirmed live ids from exploration
        for key in ("condition", "id_type", "id_number", "vehicle_number", "place"):
            assert key in ids
        cond = self.spec.field("quotation_details", "condition")
        assert cond.options.get("autocomplete") is True
        assert cond.status == "confirmed"

    def test_needs_capture_fields_marked(self):
        """Only genuinely un-captured selectors are flagged (named driver rows)."""
        owner = self.spec.section("owner")
        # owner selectors were LIVE-CAPTURED (proposal* ids) → all confirmed
        assert all(f.status == "confirmed" for f in owner.fields)
        drivers = self.spec.section("drivers")
        needs = [f.name for f in drivers.fields if f.status == "needs_capture"]
        assert needs == ["named_driver_1"]  # appears only after "Add driver"

    def test_to_fill_schema_conversion(self):
        schema = self.spec.section("owner").to_fill_schema()
        assert isinstance(schema, FillSchema)
        assert schema.name == "owner"
        fd = schema.fields["email"]
        assert fd.type == FieldType.TEXT
        assert fd.required is True

    def test_date_field_format_preserved(self):
        # dob is auto-populated by the portal from NRIC (text read-only reference)
        fd = self.spec.field("owner", "dob").to_field_definition()
        assert fd.type == FieldType.TEXT
        assert fd.required is False

    def test_transform_preserved(self):
        fd = self.spec.field("quotation_details", "vehicle_number").to_field_definition()
        assert fd.transform == "uppercase"

    def test_radio_options_preserved(self):
        fd = self.spec.field("quotation_details", "applicant_type").to_field_definition()
        assert fd.options.get("values") == ["individual", "corporate"]

    def test_required_fields_helper(self):
        req = self.spec.required_fields("quotation_details")
        assert "id_number" in req
        assert "sst_number" not in req  # optional

    def test_yaml_round_trip(self):
        """dump → load must preserve structure (for Config Studio / git diffs)."""
        text = self.spec.to_yaml()
        reloaded = MotorPrivateCarSpec.from_yaml(text)
        assert reloaded.product_id == "PMOT"
        assert [s.name for s in reloaded.sections] == [s.name for s in self.spec.sections]
        # Spot-check a field survives the round trip
        assert reloaded.field("owner", "email").selector == self.spec.field("owner", "email").selector

    def test_field_lookup_missing(self):
        assert self.spec.field("nope", "x") is None
        assert self.spec.field("owner", "nope") is None
        assert self.spec.section("nope") is None

    def test_to_fill_schemas_all_sections(self):
        schemas = self.spec.to_fill_schemas()
        assert set(schemas.keys()) == {"quotation_details", "owner", "address", "vehicle", "drivers"}
        assert all(isinstance(s, FillSchema) for s in schemas.values())

    def test_invalid_field_type_rejected(self):
        with pytest.raises(ValueError):
            FormFieldSpec(name="x", selector="#x", type="not_a_type")

    def test_invalid_status_rejected(self):
        with pytest.raises(ValueError):
            FormFieldSpec(name="x", selector="#x", status="maybe")

    def test_status_tristate_gate(self):
        """confirmed only → live; needs_capture/blocked → excluded (hard rule)."""
        c = FormFieldSpec(name="a", selector="#a", status="confirmed")
        n = FormFieldSpec(name="b", selector="#b", status="needs_capture")
        bl = FormFieldSpec(name="c", selector="#c", status="blocked")
        assert c.is_live_ready is True
        assert n.is_live_ready is False
        assert bl.is_live_ready is False

    def test_live_ready_fields_filters(self):
        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
        # quotation_details: all confirmed → all live-ready
        ready = spec.live_ready_fields("quotation_details")
        assert len(ready) == len(spec.section("quotation_details").fields)
        # owner: live-captured → all live-ready
        assert len(spec.live_ready_fields("owner")) == len(spec.section("owner").fields)
        # drivers: all_drivers_cover confirmed, named_driver_1 needs_capture
        drivers_ready = [f.name for f in spec.live_ready_fields("drivers")]
        assert "all_drivers_cover" in drivers_ready
        assert "named_driver_1" not in drivers_ready

    def test_live_schema_excludes_unconfirmed(self):
        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_YAML)
        schema = spec.live_schema("quotation_details")
        assert schema is not None
        assert "condition" in schema.fields
        # owner section now live-verified → live schema populated
        owner_schema = spec.live_schema("owner")
        assert owner_schema is not None
        assert "email" in owner_schema.fields
        # drivers: named_driver_1 (needs_capture) excluded from live schema
        drivers_schema = spec.live_schema("drivers")
        assert drivers_schema is not None
        assert "named_driver_1" not in drivers_schema.fields
        assert "all_drivers_cover" in drivers_schema.fields
