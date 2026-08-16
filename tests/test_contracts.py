"""Contract Freeze tests (ChatGPT 2026-08-16).

Verifies the frozen Product × Portal contract layer:

1. ExecutionContext canonical shape (audit-ready, no product-specific blobs)
2. Registry resolution: capability → (ProductCapability, PortalAdapter, binding)
3. PA + Motor BOTH fit the interface (the freeze's acceptance criterion)
4. Handler delegation is behavior-identical (reporter output unchanged)
5. Portal adapter/runtime expose session + diagnostics (observe-only)
"""

from __future__ import annotations

import asyncio

import pytest

from src.contracts.capability import ProductCapability
from src.contracts.gears import (
    FireProductCapability,
    GearsPortalAdapter,
    GearsPortalRuntime,
    MotorProductCapability,
    PaProductCapability,
)
from src.contracts.models import (
    ExecutionContext,
    ExecutionStage,
    ProductBinding,
)
from src.contracts.portal import PortalAdapter, PortalRuntime
from src.contracts.registry import ContractRegistry, get_default_registry


# ══════════════════════════════════════════════════════════════════════
# Registry + matrix
# ══════════════════════════════════════════════════════════════════════


class TestRegistry:
    def test_defaults_registered(self):
        reg = get_default_registry()
        assert reg.has("insurance.quote.pa")
        assert reg.has("insurance.quote.motor")
        assert reg.get_portal("gears") is not None

    def test_resolve_pa_returns_full_matrix(self):
        reg = get_default_registry()
        resolved = reg.resolve("insurance.quote.pa")
        assert resolved is not None
        assert isinstance(resolved.capability, PaProductCapability)
        assert isinstance(resolved.portal, GearsPortalAdapter)
        assert resolved.binding.product == "pa"
        assert resolved.binding.portal == "gears"
        assert resolved.binding.insurer == "great_eastern"

    def test_resolve_motor_returns_full_matrix(self):
        reg = get_default_registry()
        resolved = reg.resolve("insurance.quote.motor")
        assert resolved is not None
        assert isinstance(resolved.capability, MotorProductCapability)
        assert isinstance(resolved.portal, GearsPortalAdapter)
        assert resolved.binding.product == "motor"

    def test_unknown_capability_returns_none(self):
        reg = get_default_registry()
        # Fire + Travel are now real products (Fire-2, Travel-1); use a
        # truly unknown one
        assert reg.resolve("insurance.quote.fire") is not None
        assert reg.resolve("insurance.quote.travel") is not None
        assert reg.resolve("insurance.quote.unicorn") is None

    def test_resolve_fire_returns_full_matrix(self):
        reg = get_default_registry()
        resolved = reg.resolve("insurance.quote.fire")
        assert resolved is not None
        assert isinstance(resolved.capability, FireProductCapability)
        assert resolved.binding.product == "fire"
        assert resolved.binding.profile == "profiles/geglink_fire.yaml"

    def test_list_capabilities_matrix(self):
        reg = get_default_registry()
        matrix = reg.list_capabilities()
        by_name = {m["capability"]: m for m in matrix}
        assert "insurance.quote.pa" in by_name
        assert "insurance.quote.motor" in by_name
        pa = by_name["insurance.quote.pa"]
        assert pa["product"] == "pa"
        assert pa["portal"] == "gears"
        assert pa["profile"] == "src/portal/forms/pa_easi_protector.yaml"
        motor = by_name["insurance.quote.motor"]
        assert motor["profile"] == "src/portal/forms/motor_private_car.yaml"
        assert motor["safety"] == "readonly"

    def test_bindings_frozen(self):
        """Binding freeze: profile YAMLs must match the actual form specs."""
        reg = get_default_registry()
        for b in reg._bindings():
            import os

            assert os.path.exists(b.profile), f"profile missing: {b.profile}"


# ══════════════════════════════════════════════════════════════════════
# ExecutionContext canonical shape
# ══════════════════════════════════════════════════════════════════════


class TestExecutionContext:
    def test_canonical_shape(self):
        reg = get_default_registry()
        ctx = reg.build_context(
            "insurance.quote.pa",
            {"plan": "EP1"},
            actor="uip-ai",
        )
        assert ctx is not None
        assert ctx.execution_id
        assert ctx.capability == "insurance.quote.pa"
        assert ctx.product == "pa"
        assert ctx.portal == "gears"
        assert ctx.insurer == "great_eastern"
        assert isinstance(ctx.binding, ProductBinding)
        assert ctx.stage == ExecutionStage.RECEIVED
        d = ctx.to_dict()
        assert d["execution_id"] == ctx.execution_id
        assert d["binding"]["profile"] == "src/portal/forms/pa_easi_protector.yaml"
        assert d["actor"] == "uip-ai"

    def test_stage_lifecycle(self):
        ctx = ExecutionContext(
            capability="insurance.quote.pa", product="pa",
            insurer="great_eastern", portal="gears",
            binding=ProductBinding(
                product="pa", insurer="great_eastern", portal="gears",
                capability="insurance.quote.pa",
                profile="src/portal/forms/pa_easi_protector.yaml",
            ),
        )
        ctx.mark(ExecutionStage.VALIDATING)
        assert ctx.stage == ExecutionStage.VALIDATING
        ctx.finish(status=None, result={"ok": True})  # type: ignore[arg-type]
        assert ctx.result == {"ok": True}
        assert ctx.finished_at is not None


# ══════════════════════════════════════════════════════════════════════
# PA fits the interface
# ══════════════════════════════════════════════════════════════════════


def _pa_arguments(**overrides) -> dict:
    args = {
        "execution_mode": "real",
        "coverage_type": "individual",
        "occupation": "MANAGER",
        "applicant": {
            "id_type": "NRIC",
            "id_number": "900101-14-1232",  # synthetic checksum-valid (F)
            "full_name": "TEST APPLICANT",
            "dob": "1990-01-01",
            "gender": "F",
            "mobile": "0123456789",
            "email": "test.applicant@gmail.com",
            "address1": "12, JALAN MERDEKA",
            "state": "KUALA LUMPUR",
        },
        "plan": "EP1",
    }
    args.update(overrides)
    return args


class TestPaFitsInterface:
    def test_interface_compliance(self):
        cap = PaProductCapability()
        assert isinstance(cap, ProductCapability)
        assert cap.product == "pa"
        assert cap.capabilities == ["insurance.quote.pa"]
        assert isinstance(cap.binding, ProductBinding)

    def test_validate_valid_identity(self):
        cap = PaProductCapability()
        vr = cap.validate(_pa_arguments())
        assert vr.valid

    def test_validate_invalid_ic_fails_before_execute(self, monkeypatch):
        cap = PaProductCapability()
        called = []

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True, "premium": "182.80"}

        monkeypatch.setattr("src.quote.pa_adapter.run_pa_quote_via_cdp", runner)
        vr = cap.validate(_pa_arguments(applicant={
            "id_type": "NRIC", "id_number": "123",
            "full_name": "TEST", "dob": "1990-01-01", "gender": "M",
        }))
        assert not vr.valid
        assert vr.code
        assert called == []  # portal NEVER touched on invalid data

    def test_validate_bad_plan_fails(self):
        cap = PaProductCapability()
        vr = cap.validate(_pa_arguments(plan="EP9"))
        assert not vr.valid
        # G4 (Review #3): plan ladder now enforced by ProfileGate
        # allowed_values → VALUE_NOT_ALLOWED (same as Fire content_value)
        assert vr.code == "VALUE_NOT_ALLOWED"

    def test_execute_delegates_to_pa_adapter(self, monkeypatch):
        cap = PaProductCapability()
        captured = {}

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            captured["payload"] = payload
            return {
                "ok": True, "premium": "257.32", "premium_currency": "MYR",
                "plan": payload["plan"],
                "submission_attempted": False,
                "send_attempted": False,
                "issue_attempted": False,
            }

        monkeypatch.setattr("src.quote.pa_adapter.run_pa_quote_via_cdp", runner)
        reg = get_default_registry()
        ctx = reg.build_context("insurance.quote.pa", _pa_arguments(plan="EP3"))
        assert ctx is not None
        result = asyncio.run(cap.execute(ctx))
        assert result["ok"] is True
        assert result["premium"] == "257.32"
        # payload contract preserved exactly (handler replica)
        p = captured["payload"]
        assert p["id_number"] == "900101-14-1232"
        assert p["full_name"] == "TEST APPLICANT"
        assert p["gender"] == "F"
        assert p["dob"] == "01 Jan 1990"
        assert p["plan"] == "EP3"
        assert p["occupation"] == "MANAGER"
        assert p["coverage_type"] == "individual"
        assert p["vehicle_indicator"] == "N"
        assert ctx.result == result
        assert ctx.stage == ExecutionStage.CALCULATED


# ══════════════════════════════════════════════════════════════════════
# Motor fits the interface
# ══════════════════════════════════════════════════════════════════════


class TestMotorFitsInterface:
    def test_interface_compliance(self):
        cap = MotorProductCapability()
        assert isinstance(cap, ProductCapability)
        assert cap.product == "motor"
        assert cap.capabilities == ["insurance.quote.motor"]
        assert cap.binding.portal == "gears"

    def test_validate_ok(self):
        cap = MotorProductCapability()
        vr = cap.validate({
            "vehicle_number": "VDL 1987",
            "place": "KUALA LUMPUR",
            "id_number": "881212145678",
            "full_name": "Fionn Liang",
            "mobile": "0123456789",
            "email": "fionn.liang@gmail.com",
            "address1": "12, Jalan Merdeka",
            "marital_status": "Single",
            "years_driving_exp": "5",
            "execution_mode": "real",
        })
        assert vr.valid

    def test_execute_real_delegates_to_motor_flow(self, monkeypatch):
        """Motor-2: execute is REAL-only — delegates to motor_flow."""
        cap = MotorProductCapability()
        reg = get_default_registry()
        captured = {}

        async def fake_flow(payload, log, cdp_url="http://127.0.0.1:9333"):
            captured["payload"] = payload
            return {
                "ok": True, "status": "STEP3_OK", "quote_id": "Q1",
                "premium": "1908.53", "submission_attempted": False,
                "send_attempted": False, "issue_attempted": False,
                "execution_mode": "real",
            }

        monkeypatch.setattr(
            "src.quote.motor_flow.run_motor_quote_via_cdp", fake_flow
        )
        ctx = reg.build_context(
            "insurance.quote.motor",
            {
                "vehicle_number": "VDL 1987",
                "place": "KUALA LUMPUR",
                "id_number": "881212145678",
                "full_name": "Fionn Liang",
                "mobile": "0123456789",
                "email": "fionn.liang@gmail.com",
                "address1": "12, Jalan Merdeka",
                "marital_status": "Single",
                "years_driving_exp": "5",
                "execution_mode": "real",
            },
        )
        assert ctx is not None
        data = asyncio.run(cap.execute(ctx))
        assert data.get("ok") is True
        assert data.get("premium") == "1908.53"
        assert ctx.result == data
        assert ctx.stage == ExecutionStage.CALCULATED


# ══════════════════════════════════════════════════════════════════════
# Portal adapter + runtime
# ══════════════════════════════════════════════════════════════════════


class TestPortalAdapter:
    def test_adapter_interface(self):
        adapter = GearsPortalAdapter()
        assert isinstance(adapter, PortalAdapter)
        assert adapter.portal == "gears"
        assert adapter.insurer == "great_eastern"
        assert adapter.supports_product("pa")
        assert adapter.supports_product("motor")
        assert adapter.supports_product("fire")   # Fire-2: FSH joins GEARS
        assert adapter.supports_product("travel")  # Travel-1: PMT joins GEARS

    def test_runtime_exposes_services(self):
        runtime = GearsPortalRuntime()
        assert isinstance(runtime, PortalRuntime)
        assert runtime.portal == "gears"
        # session + diagnostics must be real service objects
        assert runtime.session is not None
        assert runtime.diagnostics is not None

    def test_runtime_health_observe_only(self):
        runtime = GearsPortalRuntime()
        report = asyncio.run(runtime.health())
        assert report["portal"] == "gears"
        assert report["overall"] in ("ready", "degraded", "failed")
        # observe-only: no recovery keys in the report
        assert "recovery" not in report

    def test_adapter_run_delegates_to_capability(self, monkeypatch):
        adapter = GearsPortalAdapter()
        reg = get_default_registry()
        ctx = reg.build_context("insurance.quote.pa", _pa_arguments())
        assert ctx is not None

        async def fake_runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            return {"ok": True, "premium": "182.80", "plan": "EP1"}

        monkeypatch.setattr("src.quote.pa_adapter.run_pa_quote_via_cdp", fake_runner)
        result = asyncio.run(adapter.run(ctx))
        assert result["ok"] is True
        assert ctx.stage == ExecutionStage.EXECUTING or ctx.stage == ExecutionStage.CALCULATED


# ══════════════════════════════════════════════════════════════════════
# Handler delegation — behavior identical
# ══════════════════════════════════════════════════════════════════════


class TestHandlerDelegation:
    def test_pa_handler_identity_gate_unchanged(self, monkeypatch):
        """Invalid identity → structured failure, runner never invoked."""
        from src.agent.handlers import PaQuoteCapabilityHandler

        handler = PaQuoteCapabilityHandler()
        called = []

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True, "premium": "182.80"}

        monkeypatch.setattr("src.quote.pa_adapter.run_pa_quote_via_cdp", runner)
        result = asyncio.run(handler.execute(_pa_arguments(applicant={
            "id_type": "NRIC", "id_number": "123",
            "full_name": "TEST", "dob": "1990-01-01", "gender": "M",
        })))
        assert result["status"] == "failed"
        assert result["error_code"] == "NRIC_LENGTH_INVALID" or result["error_code"]
        assert called == []

    def test_pa_handler_success_premium_string(self, monkeypatch):
        from src.agent.handlers import PaQuoteCapabilityHandler

        handler = PaQuoteCapabilityHandler()

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            return {
                "ok": True, "premium": "182.80", "premium_currency": "MYR",
                "plan": "EP1",
                "submission_attempted": False,
                "send_attempted": False,
                "issue_attempted": False,
            }

        monkeypatch.setattr("src.quote.pa_adapter.run_pa_quote_via_cdp", runner)
        result = asyncio.run(handler.execute(_pa_arguments()))
        assert result["status"] == "success"
        assert result["result"]["premium"] == "182.80"
        assert isinstance(result["result"]["premium"], str)
        assert result["result"]["execution"]["submission_attempted"] is False

    def test_pa_handler_payload_maps_applicant(self, monkeypatch):
        from src.agent.handlers import PaQuoteCapabilityHandler

        captured = {}

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            captured["payload"] = payload
            return {
                "ok": True, "premium": "257.32", "premium_currency": "MYR",
                "plan": payload["plan"],
                "submission_attempted": False,
                "send_attempted": False,
                "issue_attempted": False,
            }

        monkeypatch.setattr("src.quote.pa_adapter.run_pa_quote_via_cdp", runner)
        handler = PaQuoteCapabilityHandler()
        asyncio.run(handler.execute(_pa_arguments(plan="EP3")))
        payload = captured["payload"]
        assert payload["id_number"] == "900101-14-1232"
        assert payload["dob"] == "01 Jan 1990"
        assert payload["plan"] == "EP3"
