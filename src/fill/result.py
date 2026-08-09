"""InsureDesk — Fill Result Objects.

Structured results for field and section fill operations.
Used for tracing, diagnostics, and error reporting.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class FieldResult:
    """Result of filling a single field."""
    field: str = ""
    success: bool = False
    attempts: int = 0
    duration_ms: int = 0
    message: Optional[str] = None
    error: Optional[str] = None


@dataclass
class FillResult:
    """Result of filling a complete section (multiple fields)."""
    success: bool = False
    fields: list[FieldResult] = field(default_factory=list)
    section: str = ""
    duration_ms: int = 0
    total_fields: int = 0
    succeeded: int = 0
    failed: int = 0

    @property
    def summary(self) -> str:
        """Human-readable summary."""
        return (
            f"FillResult(section={self.section}, "
            f"{self.succeeded}/{self.total_fields} ok, "
            f"{self.failed} failed, "
            f"{self.duration_ms}ms)"
        )


def measure_time(func):
    """Decorator to measure execution time and return (result, duration_ms)."""
    async def wrapper(*args, **kwargs):
        start = time.monotonic()
        result = await func(*args, **kwargs)
        duration_ms = int((time.monotonic() - start) * 1000)
        return result, duration_ms
    return wrapper
