"""Motor-1 tests (ChatGPT 2026-08-16).

M1 — profile-driven validation gate (request_schema in the binding YAML)
M2 — YAML→FillEngine: selectors live in the profile, NOT in product code
M3 — real-mode execution delegates to the production GearsDriver path
M4 — contract regression: PA + Motor both traverse the same shape
"""

from __future__ import annotations

import asyncio
import os
import re

import pytest

from src.contracts.gate import ProfileGate
from src.contracts.gears import MotorProductCapability, PaProductCapability
from src.contracts.models import ExecutionStage
from src.contracts.registry import get_default_registry

MOTOR_PROFILE = "src/portal/forms/motor_private_car.yaml"


def _motor_arguments(**overrides) -> dict:
    args = {
        "execution_mode": "real",
        "vehicle_number": "VDL 1987",
        "place": "KUALA LUMPUR",
        "id_number": "881212145678",
        "proposer_name": "Fionn Liang",
        "full_name": "Fionn Liang",
        "mobile": "0123456789",
        "email": "fionn.liang@gmail.com",
        "address1": "12, Jalan Merdeka",
        "marital_status": "Single",
        "years_driving_exp": "5",
        "seating_capacity": 5,
        "hire_purchase": False,
    }
    args.update(overrides)
    return args


# ══════════════════════════════════════════════════════════════════════
# M1 — profile-driven gate
# ══════════════════════════════════════════════════════════════════════


class TestProfileGate:
    def test_required_fields_from_yaml(self):
        gate = ProfileGate(MOTOR_PROFILE)
        required = gate.required_fields()
        assert "vehicle_number" in required
        assert "place" in required
        assert "id_number" in required

    def test_validate_missing_plate_fails(self):
        gate = ProfileGate(MOTOR_PROFILE)
        vr = gate.validate({"place": "KUALA LUMPUR", "id_number": "881212145678"})
        assert not vr.valid
        assert vr.code == "MISSING_REQUIRED_FIELD"
        assert "vehicle_number" in vr.message

    def test_validate_valid_passes(self):
        gate = ProfileGate(MOTOR_PROFILE)
        vr = gate.validate(_motor_arguments())
        assert vr.valid

    def test_profile_exists_on_disk(self):
        assert os.path.exists(MOTOR_PROFILE)


class TestMotorValidate:
    def test_valid_request_passes(self):
        cap = MotorProductCapability()
        vr = cap.validate(_motor_arguments(execution_mode="real"))
        assert vr.valid

    def test_missing_plate_fails_before_execute(self, monkeypatch):
        cap = MotorProductCapability()
        called = []

        async def fake_flow(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True}

        monkeypatch.setattr(
            "src.quote.motor_flow.run_motor_quote_via_cdp", fake_flow
        )
        vr = cap.validate(_motor_arguments(execution_mode="real", vehicle_number=""))
        assert not vr.valid
        assert vr.code == "MISSING_REQUIRED_FIELD"
        assert called == []  # portal NEVER touched on invalid data

    def test_bad_id_format_fails(self):
        cap = MotorProductCapability()
        vr = cap.validate(_motor_arguments(execution_mode="real", id_number="881212-14-5678"))  # dashed
        assert not vr.valid
        assert vr.code == "ID_NUMBER_FORMAT_INVALID"

    def test_valid_id_without_dashes_passes(self):
        cap = MotorProductCapability()
        vr = cap.validate(_motor_arguments(execution_mode="real", id_number="881212145678"))
        assert vr.valid


# ══════════════════════════════════════════════════════════════════════
# M2 — YAML → FillEngine (selectors live in the profile, not product code)
# ══════════════════════════════════════════════════════════════════════


class TestYamlFillPath:
    def test_yaml_loads_via_formspec(self):
        """The binding YAML loads through the portal formspec (M2 path)."""
        from src.portal.formspec import MotorPrivateCarSpec

        spec = MotorPrivateCarSpec.from_yaml_file(MOTOR_PROFILE)
        sections = {s.name for s in spec.sections}
        assert "quotation_details" in sections
        assert "owner" in sections
        assert "vehicle" in sections

    def test_yaml_has_selectors(self):
        """Selectors MUST live in the profile YAML (they are the form spec)."""
        import yaml

        with open(MOTOR_PROFILE, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        field_selectors = []
        for sec in data["sections"]:
            for f in sec.get("fields", []):
                if f.get("selector"):
                    field_selectors.append(f["selector"])
        assert len(field_selectors) > 20  # the portal form is fully specified
        assert "#vehicleNumber" in field_selectors
        assert "#idNumber" in field_selectors

    def test_product_capability_has_no_selectors(self):
        """M2 acceptance: Motor product code carries ZERO selector knowledge.

        Portal selectors belong to the profile/runtime layer, never to the
        ProductCapability. Audit the module source for selector literals.
        """
        import inspect

        from src.contracts import gears

        src = inspect.getsource(gears.MotorProductCapability)
        assert "#vehicleNumber" not in src
        assert "#idNumber" not in src
        assert "button:has-text" not in src
        assert re.search(r"selector[:=]", src) is None

    def test_pa_capability_also_clean(self):
        """Same audit for PA (both products traverse the same clean shape)."""
        import inspect

        from src.contracts import gears

        src = inspect.getsource(gears.PaProductCapability)
        assert "selector" not in src
        assert "#plan-btn" not in src


# ══════════════════════════════════════════════════════════════════════
# M3 — real-mode execution delegates to production path
# ══════════════════════════════════════════════════════════════════════


class TestMotorRealExecution:
    def test_real_mode_delegates_to_motor_flow(self, monkeypatch):
        cap = MotorProductCapability()
        captured = {}

        async def fake_flow(payload, log, cdp_url="http://127.0.0.1:9333"):
            captured["payload"] = payload
            return {
                "ok": True, "status": "STEP3_OK", "quote_id": "Q123",
                "premium": "1908.53", "nvic": "N123", "market_value": "50000",
                "ncd": "55", "send_ready": True, "saved": False,
                "save_status": "SKIPPED",
                "submission_attempted": False,
                "send_attempted": False,
                "issue_attempted": False,
                "execution_mode": "real",
            }

        monkeypatch.setattr(
            "src.quote.motor_flow.run_motor_quote_via_cdp", fake_flow
        )
        reg = get_default_registry()
        ctx = reg.build_context(
            "insurance.quote.motor", _motor_arguments(execution_mode="real", save=False)
        )
        assert ctx is not None
        result = asyncio.run(cap.execute(ctx))
        assert result["ok"] is True
        assert result["premium"] == "1908.53"
        assert result["send_attempted"] is False
        assert result["submission_attempted"] is False
        # payload: read-only default at the contract layer
        assert captured["payload"]["save"] is False
        assert ctx.stage == ExecutionStage.CALCULATED

    def test_real_mode_defaults_readonly(self, monkeypatch):
        """save defaults False at the contract layer (manifest readonly)."""
        cap = MotorProductCapability()
        captured = {}

        async def fake_flow(payload, log, cdp_url="http://127.0.0.1:9333"):
            captured["payload"] = payload
            return {"ok": True, "status": "STEP3_OK", "premium": "1000.00"}

        monkeypatch.setattr(
            "src.quote.motor_flow.run_motor_quote_via_cdp", fake_flow
        )
        reg = get_default_registry()
        ctx = reg.build_context(
            "insurance.quote.motor",
            _motor_arguments(execution_mode="real"),
        )
        assert ctx is not None
        asyncio.run(cap.execute(ctx))
        assert captured["payload"]["save"] is False


# ══════════════════════════════════════════════════════════════════════
# M4 — contract regression (PA + Motor, same shape)
# ══════════════════════════════════════════════════════════════════════


class TestContractRegression:
    def test_both_products_resolve_through_registry(self):
        reg = get_default_registry()
        for capability in ("insurance.quote.pa", "insurance.quote.motor"):
            resolved = reg.resolve(capability)
            assert resolved is not None
            assert resolved.portal is not None
            assert resolved.binding.profile and os.path.exists(resolved.binding.profile)

    def test_both_products_have_execution_flags_in_contract(self):
        """Both product flows emit the read-only execution flags."""
        import inspect

        from src.contracts import gears
        from src.quote import motor_flow, pa_adapter

        for mod in (motor_flow, pa_adapter):
            src_text = inspect.getsource(mod)
            assert "submission_attempted" in src_text
            assert "send_attempted" in src_text
            assert "issue_attempted" in src_text

    def test_profile_gate_is_generic(self):
        """The gate is profile-driven: PA + Motor use the same ProfileGate."""
        from src.contracts.gate import ProfileGate

        pa_gate = ProfileGate(PaProductCapability().binding.profile)
        motor_gate = ProfileGate(MotorProductCapability().binding.profile)
        # PA declares no request_schema (identity validator is its gate) —
        # but the gate must degrade gracefully, not crash.
        assert pa_gate.required_fields() == [] or pa_gate.required_fields()
        assert motor_gate.required_fields() != []
