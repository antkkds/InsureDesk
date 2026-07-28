"""InsureDesk — Fill Engine Exceptions.

Structured error hierarchy for fill operations.
Each exception carries field, selector, and section context for diagnostics.
"""
from __future__ import annotations

from typing import Optional


class FillError(Exception):
    """Base fill engine error."""
    def __init__(
        self,
        message: str = "",
        field: str = "",
        selector: str = "",
        section: str = "",
        original: Optional[Exception] = None,
    ):
        self.field = field
        self.selector = selector
        self.section = section
        self.original = original
        parts = [message]
        if field:
            parts.append(f"field={field}")
        if selector:
            parts.append(f"selector={selector}")
        if section:
            parts.append(f"section={section}")
        super().__init__(" | ".join(parts))


class FieldNotFoundError(FillError):
    """Field element not found on page."""
    pass


class UnsupportedFieldTypeError(FillError):
    """Field type is not supported by any strategy."""
    def __init__(
        self,
        field_type: str = "",
        message: str = "",
        **kwargs,
    ):
        self.field_type = field_type
        msg = message or f"Unsupported field type: {field_type}"
        super().__init__(msg, **kwargs)


class FillTimeoutError(FillError):
    """Field fill operation timed out."""
    pass


class FillVerificationError(FillError):
    """Post-fill verification failed."""
    pass


class TransformationError(FillError):
    """Value transformation failed."""
    pass


class RequiredFieldMissingError(FillError):
    """Required field has no value."""
    pass


class UploadFailedError(FillError):
    """File upload failed."""
    pass
