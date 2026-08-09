"""InsureDesk — Portal Error Classification.

Standardized error types for insurance portal operations.
Used by PortalQuoteExecutor, BridgeServer, and PolicyEngine
to classify, recover, and report portal errors.

Usage:
    from src.portal.errors import PortalErrorType, PortalError, classify_error

    err = classify_error(exception, context={})
    if err.recoverable:
        # attempt recovery
    bridge_response = err.to_bridge_response(request_id)
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional, Dict, Any


class PortalErrorType(Enum):
    """Standardized portal error classifications."""
    SESSION_EXPIRED = "SESSION_EXPIRED"
    LOGIN_FAILED = "LOGIN_FAILED"
    TIMEOUT = "TIMEOUT"
    ELEMENT_NOT_FOUND = "ELEMENT_NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    CALCULATION_FAILED = "CALCULATION_FAILED"
    NAVIGATION_FAILED = "NAVIGATION_FAILED"
    NETWORK_ERROR = "NETWORK_ERROR"
    PORTAL_DOWN = "PORTAL_DOWN"
    UNKNOWN = "UNKNOWN"


# Which error types are recoverable
RECOVERABLE_ERRORS = {
    PortalErrorType.SESSION_EXPIRED,
    PortalErrorType.TIMEOUT,
    PortalErrorType.NETWORK_ERROR,
    PortalErrorType.NAVIGATION_FAILED,
}

# Which error types can auto-retry
AUTO_RETRY_ERRORS = {
    PortalErrorType.TIMEOUT,
    PortalErrorType.NETWORK_ERROR,
}


@dataclass
class PortalError:
    """Standardized portal error with classification."""
    error_type: PortalErrorType
    message: str = ""
    recoverable: bool = False
    auto_retry: bool = False
    details: Dict[str, Any] = field(default_factory=dict)
    original_error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "recoverable": self.recoverable,
            "auto_retry": self.auto_retry,
            "details": self.details,
        }

    def to_bridge_response(self, request_id: str) -> dict:
        """Format as bridge API error response."""
        return {
            "request_id": request_id,
            "status": "error",
            "error_type": self.error_type.value,
            "error": self.message,
            "recoverable": self.recoverable,
            "auto_retry": self.auto_retry,
        }


def classify_error(error: Exception, context: Optional[Dict[str, Any]] = None) -> PortalError:
    """Classify an exception into a PortalError.

    Args:
        error: The exception to classify.
        context: Optional context (action, url, etc.).

    Returns:
        PortalError with classification.
    """
    ctx = context or {}
    error_name = type(error).__name__
    error_msg = str(error)

    # Import browser errors
    try:
        from src.browser.foundation import (
            SessionExpired, RecoveryFailed,
            ElementNotVisible, NavigationFailed,
            WaitTimeout, RetryExceeded,
        )
    except ImportError:
        SessionExpired = type(None)
        RecoveryFailed = type(None)
        ElementNotVisible = type(None)
        NavigationFailed = type(None)
        WaitTimeout = type(None)
        RetryExceeded = type(None)

    # Map known exception types
    if isinstance(error, SessionExpired):
        return PortalError(
            error_type=PortalErrorType.SESSION_EXPIRED,
            message="Portal session has expired. Re-login required.",
            recoverable=True,
            auto_retry=False,
            details=ctx,
            original_error=error_msg,
        )

    if isinstance(error, (WaitTimeout, RetryExceeded)):
        return PortalError(
            error_type=PortalErrorType.TIMEOUT,
            message=f"Operation timed out: {error_msg[:200]}",
            recoverable=True,
            auto_retry=True,
            details=ctx,
            original_error=error_msg,
        )

    if isinstance(error, ElementNotVisible):
        return PortalError(
            error_type=PortalErrorType.ELEMENT_NOT_FOUND,
            message=f"Portal element not found: {error_msg[:200]}",
            recoverable=False,
            auto_retry=False,
            details=ctx,
            original_error=error_msg,
        )

    if isinstance(error, NavigationFailed):
        return PortalError(
            error_type=PortalErrorType.NAVIGATION_FAILED,
            message=f"Navigation failed: {error_msg[:200]}",
            recoverable=True,
            auto_retry=True,
            details=ctx,
            original_error=error_msg,
        )

    if isinstance(error, RecoveryFailed):
        return PortalError(
            error_type=PortalErrorType.UNKNOWN,
            message=f"Recovery exhausted: {error_msg[:200]}",
            recoverable=False,
            auto_retry=False,
            details=ctx,
            original_error=error_msg,
        )

    # Classify by message content
    msg_lower = error_msg.lower()

    if any(word in msg_lower for word in ["login", "credential", "authentication", "unauthorized"]):
        return PortalError(
            error_type=PortalErrorType.LOGIN_FAILED,
            message="Login authentication failed.",
            recoverable=False,
            auto_retry=False,
            details=ctx,
            original_error=error_msg,
        )

    if any(word in msg_lower for word in ["timeout", "timed out"]):
        return PortalError(
            error_type=PortalErrorType.TIMEOUT,
            message=f"Portal timeout: {error_msg[:200]}",
            recoverable=True,
            auto_retry=True,
            details=ctx,
            original_error=error_msg,
        )

    if any(word in msg_lower for word in ["not found", "cannot locate", "no such element"]):
        return PortalError(
            error_type=PortalErrorType.ELEMENT_NOT_FOUND,
            message=f"Expected element not found on portal page.",
            recoverable=False,
            auto_retry=False,
            details=ctx,
            original_error=error_msg,
        )

    if any(word in msg_lower for word in ["network", "connection", "dns", "refused", "reset"]):
        return PortalError(
            error_type=PortalErrorType.NETWORK_ERROR,
            message=f"Network error connecting to portal.",
            recoverable=True,
            auto_retry=True,
            details=ctx,
            original_error=error_msg,
        )

    if any(word in msg_lower for word in ["validation", "invalid field", "missing field"]):
        return PortalError(
            error_type=PortalErrorType.VALIDATION_ERROR,
            message=f"Portal validation rejected the input.",
            recoverable=False,
            auto_retry=False,
            details=ctx,
            original_error=error_msg,
        )

    if any(word in msg_lower for word in ["navigat", "redirect"]):
        return PortalError(
            error_type=PortalErrorType.NAVIGATION_FAILED,
            message=f"Page navigation issue.",
            recoverable=True,
            auto_retry=True,
            details=ctx,
            original_error=error_msg,
        )

    if any(word in msg_lower for word in ["calculate", "premium", "quote"]):
        return PortalError(
            error_type=PortalErrorType.CALCULATION_FAILED,
            message=f"Quote calculation failed on portal.",
            recoverable=False,
            auto_retry=False,
            details=ctx,
            original_error=error_msg,
        )

    # Default: Unknown
    return PortalError(
        error_type=PortalErrorType.UNKNOWN,
        message=f"Unexpected portal error: {error_msg[:200]}",
        recoverable=False,
        auto_retry=False,
        details=ctx,
        original_error=error_msg,
    )


# ══════════════════════════════════════════════════════════════════
# Timeout configuration
# ══════════════════════════════════════════════════════════════════

PORTAL_TIMEOUTS = {
    "page_load": 15.0,       # Max seconds for page navigation
    "field_fill": 5.0,       # Max seconds per field fill
    "form_submit": 15.0,     # Max seconds for form submit/calculate
    "result_extract": 10.0,  # Max seconds for result extraction
    "login": 20.0,           # Max seconds for login
    "default": 30.0,         # Default timeout
}


def get_timeout(operation: str) -> float:
    """Get timeout for a specific portal operation.

    Args:
        operation: Operation name (page_load, field_fill, etc.)

    Returns:
        Timeout in seconds.
    """
    return PORTAL_TIMEOUTS.get(operation, PORTAL_TIMEOUTS["default"])
