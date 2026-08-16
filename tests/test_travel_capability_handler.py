"""Tests for TravelProductCapability + TravelQuoteCapabilityHandler (Travel-1).

Unit level — no real portal. run_travel_quote_via_cdp is monkeypatched so the
handler logic (identity validation → payload build → result contract) is
tested deterministically. Premium must stay a STRING.
"""

from __future__ import annotations

import asyncio

import pytest

from src.agent.handlers import CapabilityHandlerRegistry, TravelQuoteCapabilityHandler
from src.contracts.gears import TravelProductCapability
from src.contracts.registry import ContractRegistry, get_default_registry


def _valid_arguments(**overrides) -> dict:
    args = {
        "execution_mode": "real",
        "trip_type": "overseas",
        "destination": "THAILAND",
        "coverage_type": "insured_only",
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
        "plan": "A",
        "adults": 1,
    }
    args.update(overrides)
    return args


def _fake_runner(result: dict):
    """Return a run_travel_quote_via_cdp replacement for the given result."""

    async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
        log("fake runner called")
        return dict(result)

    return runner


class TestCapabilityRegistration:
    def test_registered_in_defaults(self):
        reg = CapabilityHandlerRegistry()
        reg.register_defaults()
        assert reg.has("insurance.quote.travel")
        handler = reg.get("insurance.quote.travel")
        assert isinstance(handler, TravelQuoteCapabilityHandler)

    def test_registry_resolves_travel(self):
        reg = ContractRegistry()
        reg.register_defaults()
        resolved = reg.resolve("insurance.quote.travel")
        assert resolved is not None
        assert isinstance(resolved.capability, TravelProductCapability)
        assert resolved.capability.product == "travel"
        assert resolved.binding.profile.endswith("geglink_travel.yaml")
        assert resolved.binding.safety == "readonly"

    def test_gears_adapter_supports_travel(self):
        reg = get_default_registry()
        portal = reg.get_portal("gears")
        assert portal is not None
        assert portal.supports_product("travel")


class TestIdentityValidation:
    def test_invalid_ic_fails_with_code(self, monkeypatch):
        handler = TravelQuoteCapabilityHandler()
        # Should fail BEFORE the runner is invoked
        called = []

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True, "premium": "63.00"}

        monkeypatch.setattr(
            "src.quote.travel_adapter.run_travel_quote_via_cdp", runner
        )
        result = asyncio.run(
            handler.execute(
                _valid_arguments(
                    applicant={
                        "id_type": "NRIC",
                        "id_number": "123",  # invalid
                        "full_name": "TEST",
                        "dob": "1990-01-01",
                        "gender": "M",
                    }
                )
            )
        )
        assert result["status"] == "failed"
        assert not called, "runner must not be invoked for invalid identity"

    def test_missing_id_number_fails(self, monkeypatch):
        handler = TravelQuoteCapabilityHandler()
        called = []

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True, "premium": "63.00"}

        monkeypatch.setattr(
            "src.quote.travel_adapter.run_travel_quote_via_cdp", runner
        )
        result = asyncio.run(
            handler.execute(
                _valid_arguments(
                    applicant={
                        "id_type": "NRIC",
                        "id_number": "",
                        "full_name": "TEST",
                    }
                )
            )
        )
        assert result["status"] == "failed"
        assert not called

    def test_bad_plan_fails(self, monkeypatch):
        handler = TravelQuoteCapabilityHandler()
        called = []

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True, "premium": "63.00"}

        monkeypatch.setattr(
            "src.quote.travel_adapter.run_travel_quote_via_cdp", runner
        )
        result = asyncio.run(handler.execute(_valid_arguments(plan="Z")))
        assert result["status"] == "failed"
        assert not called

    def test_bad_trip_type_fails(self, monkeypatch):
        handler = TravelQuoteCapabilityHandler()
        result = asyncio.run(
            handler.execute(_valid_arguments(trip_type="moon"))
        )
        assert result["status"] == "failed"


class TestSuccessPath:
    def test_success_premium_is_string(self, monkeypatch):
        handler = TravelQuoteCapabilityHandler()
        monkeypatch.setattr(
            "src.quote.travel_adapter.run_travel_quote_via_cdp",
            _fake_runner(
                {
                    "ok": True,
                    "status": "TRAVEL_E2E_COMPLETE",
                    "quote_status": "calculated",
                    "premium": "63.00",
                    "premium_currency": "MYR",
                    "plan": "A",
                    "submission_attempted": False,
                    "send_attempted": False,
                    "issue_attempted": False,
                }
            ),
        )
        result = asyncio.run(handler.execute(_valid_arguments()))
        assert result["status"] == "success"
        data = result["result"]
        assert data["premium"] == "63.00"
        assert isinstance(data["premium"], str)
        assert data["status"] == "calculated"
        assert data["product"] == "TRAVEL_FOR_MORE_PLUS"
        assert data["execution"]["mode"] == "real"
        assert data["execution"]["submission_attempted"] is False
        assert data["execution"]["send_attempted"] is False
        assert data["execution"]["issue_attempted"] is False

    def test_runner_failure_is_propagated(self, monkeypatch):
        handler = TravelQuoteCapabilityHandler()
        monkeypatch.setattr(
            "src.quote.travel_adapter.run_travel_quote_via_cdp",
            _fake_runner({"ok": False, "error": "portal timeout"}),
        )
        result = asyncio.run(handler.execute(_valid_arguments()))
        assert result["status"] == "failed"
        assert "portal timeout" in result["error"]

    def test_payload_maps_applicant(self, monkeypatch):
        """The capability payload must carry applicant fields into the flow."""
        handler = TravelQuoteCapabilityHandler()
        captured = {}

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            captured["payload"] = dict(payload)
            return {
                "ok": True,
                "premium": "63.00",
                "premium_currency": "MYR",
                "plan": "A",
                "submission_attempted": False,
                "send_attempted": False,
                "issue_attempted": False,
            }

        monkeypatch.setattr(
            "src.quote.travel_adapter.run_travel_quote_via_cdp", runner
        )
        asyncio.run(
            handler.execute(
                _valid_arguments(
                    applicant={
                        "id_type": "NRIC",
                        "id_number": "900101-14-1232",
                        "full_name": "TEST APPLICANT",
                        "dob": "1990-01-01",
                        "gender": "F",
                        "nationality": "MALAYSIAN",
                        "state": "KUALA LUMPUR",
                        "mobile": "0123456789",
                        "email": "test.applicant@gmail.com",
                        "address1": "12, JALAN MERDEKA",
                    }
                )
            )
        )
        p = captured["payload"]
        assert p["id_number"] == "900101-14-1232"
        assert p["full_name"] == "TEST APPLICANT"
        assert p["trip_type"] == "overseas"
        assert p["destination"] == "THAILAND"
        assert p["plan"] == "A"


class TestProfileGate:
    def test_validate_ok(self):
        cap = TravelProductCapability()
        vr = cap.validate(_valid_arguments())
        assert vr.valid

    def test_validate_missing_required(self):
        cap = TravelProductCapability()
        args = _valid_arguments()
        del args["destination"]
        vr = cap.validate(args)
        assert not vr.valid

    def test_validate_allowed_plan(self):
        cap = TravelProductCapability()
        for plan in ("A", "B", "C"):
            vr = cap.validate(_valid_arguments(plan=plan))
            assert vr.valid, f"plan {plan} should pass"
