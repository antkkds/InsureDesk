"""Tests for the WSL GEARS CLI bridge (scripts/gears_cli.py).

Pure-function tests only — no browser, no live portal. The live flow is
covered by manual runs (see skill: live verification with real quote).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from gears_cli import build_result, parse_payload


class TestParsePayload:
    def test_empty_payload_uses_defaults(self):
        p, err = parse_payload("{}")
        assert err is None
        assert p["vehicle_number"] == "TEST123"
        assert p["hire_purchase"] is False
        assert p["save"] is True

    def test_overrides(self):
        p, err = parse_payload('{"vehicle_number":"WKL1234","full_name":"Alice"}')
        assert err is None
        assert p["vehicle_number"] == "WKL1234"
        assert p["full_name"] == "Alice"
        assert p["hire_purchase"] is False  # untouched default

    def test_boolean_strings_coerced(self):
        p, _ = parse_payload(
            '{"hire_purchase":"true","save":"0","add_ons":"no"}'
        )
        assert p["hire_purchase"] is True
        assert p["save"] is False
        assert p["add_ons"] is False

    def test_int_strings_coerced(self):
        p, _ = parse_payload('{"year_manufacture":"2019","seating_capacity":"7"}')
        assert p["year_manufacture"] == 2019
        assert p["seating_capacity"] == 7

    def test_bad_int_falls_back_to_default(self):
        p, _ = parse_payload('{"year_manufacture":"abc"}')
        assert p["year_manufacture"] == 2024

    def test_invalid_json(self):
        p, err = parse_payload("not json")
        assert p is None
        assert "not valid JSON" in err

    def test_non_object_json(self):
        p, err = parse_payload("[1,2,3]")
        assert p is None
        assert "must be a JSON object" in err

    def test_blank_vehicle_rejected(self):
        p, err = parse_payload('{"vehicle_number":""}')
        assert err is not None
        assert "vehicle_number is required" in err

    def test_none_values_do_not_override(self):
        p, _ = parse_payload('{"vehicle_number":null,"hire_purchase":null}')
        assert p["vehicle_number"] == "TEST123"
        assert p["hire_purchase"] is False


class TestBuildResult:
    def test_defaults_are_stable_keys(self):
        r = build_result()
        assert set(r) == {
            "ok", "status", "quote_id", "quote_url", "step", "referred",
            "market_available", "send_ready", "saved", "save_status",
            "doc_name", "version", "send_status", "send_email", "send_http",
            "error", "elapsed",
        }
        assert r["ok"] is False

    def test_overrides(self):
        r = build_result(status="SAVED", saved=True, quote_id="abc")
        assert r["status"] == "SAVED"
        assert r["saved"] is True
        assert r["quote_id"] == "abc"
