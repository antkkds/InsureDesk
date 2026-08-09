"""InsureDesk — ActionResult: structured per-action diagnostics.

Every PortalDriver interaction returns an ActionResult so executions are
fully observable: success/failure, timing, attempts, and a trace of
sub-steps (retries, fallbacks, verification reads).

Design notes (from ChatGPT review 2026-08):
    - Keep it thin: ActionResult is a *result*, not a workflow engine.
      Step orchestration lives in FormSpec/ExecutionEngine.
    - trace events accumulate sub-steps so failures can be replayed
      without re-running the browser.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import time


@dataclass
class TraceEvent:
    """One observable sub-step during an action.

    Examples:
        ("attempt",  "fill #vehicleNumber", "ok", 42)
        ("verify",   "read #vehicleNumber", "ok", 5)
        ("retry",    "fill #condition",     "timeout", 3000)
    """
    kind: str                       # attempt | verify | retry | fallback | navigation
    target: str                     # selector / url / description
    status: str                     # ok | failed | timeout | skipped
    duration_ms: int = 0
    detail: str = ""
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "target": self.target,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "detail": self.detail,
            "ts": self.ts,
        }


@dataclass
class ActionResult:
    """Structured outcome of a single driver action."""

    action: str                     # navigate | fill | select | click | read | wait_for
    success: bool = False
    selector: str = ""              # element / url the action targeted
    message: str = ""               # human-readable summary
    error: Optional[str] = None     # machine-readable error code/message
    duration_ms: int = 0
    attempts: int = 1
    value: Optional[Any] = None     # payload (read value, screenshot bytes, ...)
    trace: list[TraceEvent] = field(default_factory=list)

    # --- convenience -------------------------------------------------

    @classmethod
    def ok(
        cls,
        action: str,
        selector: str = "",
        message: str = "OK",
        duration_ms: int = 0,
        value: Any = None,
    ) -> "ActionResult":
        return cls(
            action=action,
            success=True,
            selector=selector,
            message=message,
            duration_ms=duration_ms,
            value=value,
        )

    @classmethod
    def fail(
        cls,
        action: str,
        selector: str = "",
        error: str = "unknown error",
        message: str = "",
        duration_ms: int = 0,
    ) -> "ActionResult":
        return cls(
            action=action,
            success=False,
            selector=selector,
            error=error,
            message=message or error,
            duration_ms=duration_ms,
        )

    def add_trace(self, event: TraceEvent) -> None:
        """Append a trace event."""
        self.trace.append(event)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "success": self.success,
            "selector": self.selector,
            "message": self.message,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "attempts": self.attempts,
            "trace": [t.to_dict() for t in self.trace],
        }

    @property
    def summary(self) -> str:
        """One-line human summary."""
        status = "ok" if self.success else "FAILED"
        loc = f" [{self.selector}]" if self.selector else ""
        err = f" — {self.error}" if self.error else ""
        return f"{self.action}{loc} {status} ({self.duration_ms}ms){err}"
