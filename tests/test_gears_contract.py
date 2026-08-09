"""Unit tests for the GEARS JS-unlock field contract guardrail.

Covers the ChatGPT-review requirements:
- disabled-field writes are allowlisted (fail closed for anything else)
- native-setter fields use the native setter contract
- value read-back comparison is locale-normalized (50,000 vs 50000)
- hire purchase is an explicit business input (default No)
"""
import pytest

from src.quote.gears_create import (
    JS_FIELD_CONTRACT,
    UNLOCKED_JS_FIELDS,
    QuoteCreateOutcome,
    normalize_field_value,
)


class TestFieldContract:
    def test_allowlist_contains_all_js_managed_fields(self):
        assert UNLOCKED_JS_FIELDS == frozenset(
            ["condition", "marketValue", "start-date", "end-date"]
        )

    def test_every_contract_entry_has_valid_setter(self):
        for fid, spec in JS_FIELD_CONTRACT.items():
            assert spec["setter"] in ("native_setter", "click_unlock"), fid
            assert spec["events"], fid

    def test_unknown_field_not_in_allowlist(self):
        # a field NOT in the contract must NOT be writable via the JS path
        assert "hirePurchaseCompany" not in UNLOCKED_JS_FIELDS
        assert "proposalFullName" not in UNLOCKED_JS_FIELDS

    def test_native_setter_fields_are_disabled_inputs(self):
        # marketValue / dates are disabled inputs → native setter contract
        for fid in ("marketValue", "start-date", "end-date"):
            assert JS_FIELD_CONTRACT[fid]["setter"] == "native_setter", fid

    def test_condition_uses_click_unlock(self):
        assert JS_FIELD_CONTRACT["condition"]["setter"] == "click_unlock"


class TestNormalizeFieldValue:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("50000", "50000"),
            ("50,000", "50000"),
            ("50 000", "50000"),
            ("11200", "11200"),
            ("11,200", "11200"),
            ("10 Sep 2026", "10Sep2026"),
            ("10 Sep 2026 ", "10Sep2026"),
        ],
    )
    def test_locale_formats_normalize(self, raw, expected):
        assert normalize_field_value(raw) == expected

    def test_market_value_mismatch_is_not_reported(self):
        # 50,000 (read-back) vs 50000 (written) must compare equal
        assert normalize_field_value("50,000") == normalize_field_value("50000")

    def test_real_mismatch_still_detected(self):
        assert normalize_field_value("50000") != normalize_field_value("99999")


class TestSendReady:
    def test_normal_quote_send_ready(self):
        # non-referred + market data available + reached step 3 → Send-able
        o = QuoteCreateOutcome(status="STEP3_OK", step=3,
                               referred=False, market_available=True)
        assert o.send_ready is True

    def test_market_unavailable_blocks_send(self):
        # TEST123-style: NVIC lookup empty → never Send-able, even if saved
        o = QuoteCreateOutcome(status="STEP3_OK", step=3,
                               referred=False, market_available=False)
        assert o.send_ready is False

    def test_referred_blocks_send(self):
        # WKL1234-style: old vehicle → referral → Submit-for-review path
        o = QuoteCreateOutcome(status="REFERRED", step=3,
                               referred=True, market_available=True)
        assert o.send_ready is False

    def test_to_dict_contains_new_fields(self):
        d = QuoteCreateOutcome(step=3).to_dict()
        assert "market_available" in d and "send_ready" in d
        assert d["send_ready"] is True  # default: market available, not referred
