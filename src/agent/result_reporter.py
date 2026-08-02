"""InsureDesk — Agent Result Reporter.

Unified result format for the UIP-AI Agent Protocol (Phase 4.3).

Success:
    {"status": "success", "result": {...}, "execution_mode": "real"|"simulation"}

Failure:
    {"status": "failed", "error_code": "PORTAL_AUTH_FAILED", "error": "..."}

Never send raw exceptions — map local errors to stable protocol codes.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

# Local error → protocol error code mapping (T5) + retryable hints
ERROR_CODE_MAP = {
    "login_failed": ("PORTAL_AUTH_FAILED", True),
    "auth_failed": ("PORTAL_AUTH_FAILED", True),
    "session_expired": ("PORTAL_SESSION_EXPIRED", True),
    "login_required": ("LOGIN_REQUIRED", True),
    "captcha": ("CAPTCHA_REQUIRED", True),
    "portal_changed": ("PORTAL_CHANGED", False),
    "not_found": ("NOT_FOUND", False),
    "timeout": ("PORTAL_TIMEOUT", True),
    "network": ("NETWORK_ERROR", True),
    "validation_error": ("VALIDATION_ERROR", False),
}

DEFAULT_ERROR = ("EXECUTION_FAILED", False)


def map_error_code(error: str | Exception) -> str:
    """Map a local error string/exception to a stable protocol code."""
    code, _ = map_error(error)
    return code


def map_error(error: str | Exception) -> tuple[str, bool]:
    """Map a local error to (protocol_code, retryable)."""
    text = str(error).lower().replace(" ", "_").replace("-", "_")
    for key, (code, retryable) in ERROR_CODE_MAP.items():
        if key in text:
            return code, retryable
    return DEFAULT_ERROR


class ResultReporter:
    """Builds protocol-standard result payloads."""

    def success(
        self,
        result: Any,
        execution_mode: str = "simulation",
    ) -> Dict[str, Any]:
        return {
            "status": "success",
            "result": result,
            "execution_mode": execution_mode,
        }

    def failed(
        self,
        error: str | Exception,
        error_code: Optional[str] = None,
        retryable: Optional[bool] = None,
    ) -> Dict[str, Any]:
        code, default_retryable = map_error(error)
        return {
            "status": "failed",
            "error_code": error_code or code,
            "error": str(error),
            "retryable": default_retryable if retryable is None else retryable,
        }

    def blocked(self, capability: str) -> Dict[str, Any]:
        """Safety-policy block (Phase 4.5 T5 — READ_ONLY_BLOCKED)."""
        return {
            "status": "failed",
            "error_code": "READ_ONLY_BLOCKED",
            "error": f"Capability '{capability}' is blocked by execution policy "
                     f"(readonly)",
            "retryable": False,
        }
