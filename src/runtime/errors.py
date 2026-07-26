"""InsureDesk Runtime — Normalized Error Types.

Every adapter, selector, and executor raises ExtractionErrors
with a consistent error code and structured context.
"""

from typing import Optional, Dict, Any


class ExtractionError(Exception):
    """Normalized extraction error with machine-readable code.

    Attributes:
        code: Machine-readable error code (e.g. 'adapter_not_found')
        message: Human-readable description
        context: Additional structured context (e.g. available adapters)
    """

    def __init__(self, code: str, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.context = context or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": str(self),
            "context": self.context,
        }

    def __str__(self) -> str:
        return f"[{self.code}] {self.args[0]}"

    def __repr__(self) -> str:
        return f"ExtractionError({self.code!r}, {self.args[0]!r})"


class AdapterNotFoundError(ExtractionError):
    """No adapter supports the given portal or data."""

    def __init__(self, portal_hint: str = "", available: list = None):
        super().__init__(
            code="adapter_not_found",
            message=f"No adapter found for portal: {portal_hint or 'auto-detect'}"
                     f" (available: {len(available or [])})",
            context={
                "portal_hint": portal_hint,
                "available_adapters": [a["name"] for a in (available or [])],
            },
        )


class ValidationFailedError(ExtractionError):
    """Extraction succeeded but validation failed."""

    def __init__(self, entity_type: str, errors: list):
        super().__init__(
            code="validation_failed",
            message=f"{entity_type} validation failed: {len(errors)} issue(s)",
            context={"entity_type": entity_type, "validation_errors": [str(e) for e in errors]},
        )


class MissingDataError(ExtractionError):
    """Raw data is missing required fields for any adapter to work."""

    def __init__(self, top_keys: list):
        super().__init__(
            code="missing_data",
            message=f"Raw data has {len(top_keys)} top-level key(s) — too sparse for auto-detection",
            context={"top_keys": top_keys[:20]},
        )


class AdapterExecutionError(ExtractionError):
    """Adapter raised an unexpected error during extraction."""

    def __init__(self, adapter_name: str, original_error: str):
        super().__init__(
            code="adapter_execution_error",
            message=f"Adapter '{adapter_name}' raised: {original_error}",
            context={"adapter_name": adapter_name, "original_error": original_error},
        )


class CapabilityNotSupportedError(ExtractionError):
    """The adapter does not support the requested capability."""

    def __init__(self, adapter_name: str, capability: str):
        super().__init__(
            code="capability_not_supported",
            message=f"Adapter '{adapter_name}' does not support capability '{capability}'",
            context={"adapter_name": adapter_name, "capability": capability},
        )
