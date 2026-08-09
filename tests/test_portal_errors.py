"""Tests: Sprint 5.3 — Portal Error Recovery.

Tests for:
1. PortalErrorType — enum values, recoverable sets
2. PortalError — dataclass, to_dict, to_bridge_response
3. classify_error — exception → PortalError mapping
4. Timeout configuration
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. PortalErrorType (4 tests)
# ══════════════════════════════════════════════════════════════════


class TestPortalErrorType:
    """Error type enum."""

    def test_values(self):
        from src.portal.errors import PortalErrorType
        assert PortalErrorType.SESSION_EXPIRED.value == "SESSION_EXPIRED"
        assert PortalErrorType.TIMEOUT.value == "TIMEOUT"
        assert PortalErrorType.ELEMENT_NOT_FOUND.value == "ELEMENT_NOT_FOUND"
        assert PortalErrorType.VALIDATION_ERROR.value == "VALIDATION_ERROR"
        assert PortalErrorType.UNKNOWN.value == "UNKNOWN"

    def test_all_types_present(self):
        from src.portal.errors import PortalErrorType
        assert len(PortalErrorType) == 10

    def test_recoverable_errors(self):
        from src.portal.errors import RECOVERABLE_ERRORS, PortalErrorType
        assert PortalErrorType.SESSION_EXPIRED in RECOVERABLE_ERRORS
        assert PortalErrorType.TIMEOUT in RECOVERABLE_ERRORS
        assert PortalErrorType.NETWORK_ERROR in RECOVERABLE_ERRORS
        assert PortalErrorType.NAVIGATION_FAILED in RECOVERABLE_ERRORS
        assert PortalErrorType.ELEMENT_NOT_FOUND not in RECOVERABLE_ERRORS
        assert PortalErrorType.UNKNOWN not in RECOVERABLE_ERRORS

    def test_auto_retry_errors(self):
        from src.portal.errors import AUTO_RETRY_ERRORS, PortalErrorType
        assert PortalErrorType.TIMEOUT in AUTO_RETRY_ERRORS
        assert PortalErrorType.NETWORK_ERROR in AUTO_RETRY_ERRORS
        assert PortalErrorType.SESSION_EXPIRED not in AUTO_RETRY_ERRORS


# ══════════════════════════════════════════════════════════════════
# 2. PortalError (4 tests)
# ══════════════════════════════════════════════════════════════════


class TestPortalError:
    """PortalError dataclass."""

    def test_defaults(self):
        from src.portal.errors import PortalError, PortalErrorType
        err = PortalError(error_type=PortalErrorType.TIMEOUT)
        assert err.error_type == PortalErrorType.TIMEOUT
        assert err.message == ""
        assert err.recoverable is False
        assert err.auto_retry is False

    def test_to_dict(self):
        from src.portal.errors import PortalError, PortalErrorType
        err = PortalError(
            error_type=PortalErrorType.SESSION_EXPIRED,
            message="Session expired",
            recoverable=True,
            details={"url": "/get-quote"},
        )
        d = err.to_dict()
        assert d["error_type"] == "SESSION_EXPIRED"
        assert d["recoverable"] is True
        assert d["details"]["url"] == "/get-quote"

    def test_to_bridge_response(self):
        from src.portal.errors import PortalError, PortalErrorType
        err = PortalError(
            error_type=PortalErrorType.SESSION_EXPIRED,
            message="Please re-login",
            recoverable=True,
        )
        resp = err.to_bridge_response("req-001")
        assert resp["request_id"] == "req-001"
        assert resp["status"] == "error"
        assert resp["error_type"] == "SESSION_EXPIRED"
        assert resp["recoverable"] is True

    def test_recoverable_flag_from_set(self):
        from src.portal.errors import PortalError, PortalErrorType, RECOVERABLE_ERRORS
        for etype in RECOVERABLE_ERRORS:
            err = PortalError(error_type=etype, message="", recoverable=True)
            assert err.recoverable is True


# ══════════════════════════════════════════════════════════════════
# 3. classify_error (12 tests)
# ══════════════════════════════════════════════════════════════════


class TestClassifyError:
    """Exception → PortalError classification."""

    def test_session_expired(self):
        from src.portal.errors import classify_error, PortalErrorType
        try:
            from src.browser.foundation import SessionExpired
            err = classify_error(SessionExpired("session gone"))
        except ImportError:
            # Fallback if browser.foundation not available
            err = classify_error(
                Exception("Login required: session has expired"),
            )
        assert err.error_type == PortalErrorType.SESSION_EXPIRED
        assert err.recoverable is True

    def test_timeout_exception(self):
        from src.portal.errors import classify_error, PortalErrorType
        try:
            from src.browser.foundation import WaitTimeout
            err = classify_error(WaitTimeout("element not visible after 15s"))
        except ImportError:
            err = classify_error(Exception("Operation timed out after 30 seconds"))
        assert err.error_type == PortalErrorType.TIMEOUT
        assert err.recoverable is True
        assert err.auto_retry is True

    def test_element_not_visible(self):
        from src.portal.errors import classify_error, PortalErrorType
        try:
            from src.browser.foundation import ElementNotVisible
            err = classify_error(ElementNotVisible("selector not found"))
        except ImportError:
            err = classify_error(Exception("No such element: #f_insured_name"))
        assert err.error_type == PortalErrorType.ELEMENT_NOT_FOUND
        assert err.recoverable is False

    def test_navigation_failed(self):
        from src.portal.errors import classify_error, PortalErrorType
        err = classify_error(Exception("Failed to navigate to https://geglink.com"))
        # "navigat" keyword should match
        assert err.error_type == PortalErrorType.NAVIGATION_FAILED
        assert err.recoverable is True

    def test_login_failed_by_message(self):
        from src.portal.errors import classify_error, PortalErrorType
        err = classify_error(Exception("Login failed: invalid credentials"))
        assert err.error_type == PortalErrorType.LOGIN_FAILED
        assert err.recoverable is False

    def test_network_error(self):
        from src.portal.errors import classify_error, PortalErrorType
        err = classify_error(Exception("Connection refused: geglink.com:443"))
        assert err.error_type == PortalErrorType.NETWORK_ERROR
        assert err.recoverable is True
        assert err.auto_retry is True

    def test_validation_error(self):
        from src.portal.errors import classify_error, PortalErrorType
        err = classify_error(Exception("Validation error: Invalid sum insured"))
        assert err.error_type == PortalErrorType.VALIDATION_ERROR
        assert err.recoverable is False

    def test_calculation_failed(self):
        from src.portal.errors import classify_error, PortalErrorType
        err = classify_error(Exception("Quote calculation failed: occupation missing"))
        assert err.error_type == PortalErrorType.CALCULATION_FAILED
        assert err.recoverable is False

    def test_unknown_error_default(self):
        from src.portal.errors import classify_error, PortalErrorType
        err = classify_error(Exception("Some random error"))
        assert err.error_type == PortalErrorType.UNKNOWN
        assert err.recoverable is False

    def test_unknown_error_without_keywords(self):
        from src.portal.errors import classify_error, PortalErrorType
        err = classify_error(ValueError("invalid literal for int() with base 10"))
        assert err.error_type == PortalErrorType.UNKNOWN

    def test_context_passed_to_details(self):
        from src.portal.errors import classify_error
        err = classify_error(Exception("timeout"), context={"action": "calculate", "url": "/fireQuote"})
        assert err.details.get("action") == "calculate"

    def test_error_messages_truncated(self):
        from src.portal.errors import classify_error
        long_msg = "x" * 500
        err = classify_error(Exception(long_msg))
        assert len(err.original_error) <= 500


# ══════════════════════════════════════════════════════════════════
# 4. Timeout configuration (3 tests)
# ══════════════════════════════════════════════════════════════════


class TestPortalTimeouts:
    """Timeout configuration."""

    def test_get_timeout_known(self):
        from src.portal.errors import get_timeout
        assert get_timeout("page_load") == 15.0
        assert get_timeout("field_fill") == 5.0
        assert get_timeout("form_submit") == 15.0
        assert get_timeout("login") == 20.0

    def test_get_timeout_unknown(self):
        from src.portal.errors import get_timeout
        assert get_timeout("nonexistent") == 30.0  # default

    def test_get_timeout_result_extract(self):
        from src.portal.errors import get_timeout
        assert get_timeout("result_extract") == 10.0
