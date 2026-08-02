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

# Local error → protocol error code mapping (T5)
ERROR_CODE_MAP = {
    "login_failed": "PORTAL_AUTH_FAILED",
    "auth_failed": "PORTAL_AUTH_FAILED",
    "session_expired": "PORTAL_SESSION_EXPIRED",
    "not_found": "NOT_FOUND",
    "timeout": "PORTAL_TIMEOUT",
    "validation_error": "VALIDATION_ERROR",
}


def map_error_code(error: str | Exception) -> str:
    """Map a local error string/exception to a stable protocol code."""
    text = str(error).lower().replace(" ", "_").replace("-", "_")
    for key, code in ERROR_CODE_MAP.items():
        if key in text:
            return code
    return "EXECUTION_FAILED"


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
    ) -> Dict[str, Any]:
        return {
            "status": "failed",
            "error_code": error_code or map_error_code(error),
            "error": str(error),
        }
