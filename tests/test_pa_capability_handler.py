"""Tests for PaQuoteCapabilityHandler (PA-6, insurance.quote.pa).

Unit level — no real portal. run_pa_quote_via_cdp is monkeypatched so the
handler logic (identity validation → payload build → result contract) is
tested deterministically. Premium must stay a STRING.
"""

from __future__ import annotations

import asyncio

import pytest

from src.agent.handlers import CapabilityHandlerRegistry, PaQuoteCapabilityHandler


def _valid_arguments(**overrides) -> dict:
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


def _fake_runner(result: dict):
    """Return a run_pa_quote_via_cdp replacement for the given result."""

    async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
        log("fake runner called")
        return dict(result)

    return runner


class TestCapabilityRegistration:
    def test_registered_in_defaults(self):
        reg = CapabilityHandlerRegistry()
        reg.register_defaults()
        assert reg.has("insurance.quote.pa")
        handler = reg.get("insurance.quote.pa")
        assert isinstance(handler, PaQuoteCapabilityHandler)


class TestIdentityValidation:
    def test_invalid_ic_fails_with_code(self, monkeypatch):
        handler = PaQuoteCapabilityHandler()
        # Should fail BEFORE the runner is invoked
        called = []

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            called.append(True)
            return {"ok": True, "premium": "182.80"}

        monkeypatch.setattr(
            "src.quote.pa_adapter.run_pa_quote_via_cdp", runner
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
        assert result["error_code"] == "IC_FORMAT"
        assert called == []  # runner never invoked

    def test_missing_id_number_fails(self, monkeypatch):
        handler = PaQuoteCapabilityHandler()
        result = asyncio.run(
            handler.execute(
                _valid_arguments(
                    applicant={"id_type": "NRIC", "id_number": "", "full_name": "X"}
                )
            )
        )
        assert result["status"] == "failed"
        assert result["error_code"] == "IDENTITY_REQUIREMENT_MISSING"

    def test_bad_plan_fails(self, monkeypatch):
        handler = PaQuoteCapabilityHandler()
        result = asyncio.run(handler.execute(_valid_arguments(plan="EP9")))
        assert result["status"] == "failed"
        # G4 (Review #3): plan ladder enforced by ProfileGate allowed_values
        assert result["error_code"] == "VALUE_NOT_ALLOWED"


class TestSuccessContract:
    def test_success_premium_is_string(self, monkeypatch):
        handler = PaQuoteCapabilityHandler()
        monkeypatch.setattr(
            "src.quote.pa_adapter.run_pa_quote_via_cdp",
            _fake_runner(
                {
                    "ok": True,
                    "status": "PA_E2E_COMPLETE",
                    "quote_status": "calculated",
                    "premium": "182.80",
                    "premium_currency": "MYR",
                    "plan": "EP1",
                    "submission_attempted": False,
                    "send_attempted": False,
                    "issue_attempted": False,
                }
            ),
        )
        result = asyncio.run(handler.execute(_valid_arguments()))
        assert result["status"] == "success"
        assert result["execution_mode"] == "real"
        payload = result["result"]
        assert payload["status"] == "calculated"
        assert payload["product"] == "EASI_PROTECTOR"
        assert payload["plan"] == "EP1"
        assert payload["premium"] == "182.80"
        assert isinstance(payload["premium"], str)
        assert payload["currency"] == "MYR"
        assert payload["execution"]["mode"] == "real"
        assert payload["execution"]["submission_attempted"] is False
        assert payload["execution"]["send_attempted"] is False
        assert payload["execution"]["issue_attempted"] is False

    def test_runner_failure_is_propagated(self, monkeypatch):
        handler = PaQuoteCapabilityHandler()
        monkeypatch.setattr(
            "src.quote.pa_adapter.run_pa_quote_via_cdp",
            _fake_runner({"ok": False, "error": "no GEARS tab found in CDP"}),
        )
        result = asyncio.run(handler.execute(_valid_arguments()))
        assert result["status"] == "failed"
        assert result["error_code"] == "PA_QUOTE_FAILED"
        assert "no GEARS tab" in result["error"]


class TestPayloadBuild:
    def test_payload_maps_applicant(self, monkeypatch):
        captured = {}

        async def runner(payload, log, cdp_url="http://127.0.0.1:9333"):
            captured["payload"] = payload
            return {
                "ok": True,
                "premium": "257.32",
                "premium_currency": "MYR",
                "plan": payload["plan"],
                "submission_attempted": False,
                "send_attempted": False,
                "issue_attempted": False,
            }

        monkeypatch.setattr(
            "src.quote.pa_adapter.run_pa_quote_via_cdp", runner
        )
        handler = PaQuoteCapabilityHandler()
        asyncio.run(handler.execute(_valid_arguments(plan="EP3")))
        payload = captured["payload"]
        assert payload["id_number"] == "900101-14-1232"
        assert payload["full_name"] == "TEST APPLICANT"
        assert payload["gender"] == "F"
        assert payload["dob"] == "01 Jan 1990"
        assert payload["plan"] == "EP3"
        assert payload["occupation"] == "MANAGER"
        assert payload["coverage_type"] == "individual"
