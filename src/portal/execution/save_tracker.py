"""InsureDesk — Save Failure Observability.

Connects the portal SAVE boundary into the same ActionResult/TraceEvent
trace as field filling (ChatGPT review 2026-08, emphasis):

    fill → verify → SAVE → verify persisted state

The SaveTracker records every Save/Submit request's HTTP layer signals
(status, response body, correlation ids) as TraceEvents. When a save
fails with a generic server error ("all fields correct but server says
generic error"), the trace now contains the full picture — no more
black-box failures.

Usage:
    tracker = SaveTracker()
    tracker.begin("save_quote")
    try:
        resp = await page.request.post(url, data=payload)
        tracker.record_http(resp.status, await resp.text(), url)
    except Exception as e:
        tracker.record_exception(e)
    events = tracker.events()   # → list[TraceEvent], merge into execution trace
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
import time

from src.portal.action_result import TraceEvent


@dataclass
class SaveRecord:
    """One save/submit attempt with full HTTP observability."""

    attempt: int = 0
    url: str = ""
    method: str = "POST"
    status: Optional[int] = None          # HTTP status (None = network error)
    response_body: str = ""               # first N chars of response
    correlation_id: Optional[str] = None  # server-side trace id if present
    duration_ms: int = 0
    error: Optional[str] = None
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "url": self.url,
            "method": self.method,
            "status": self.status,
            "response_body": self.response_body[:500],
            "correlation_id": self.correlation_id,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }


class SaveTracker:
    """Accumulates save-attempt HTTP signals into TraceEvents.

    Trace kinds emitted:
        save_request    — a save POST was issued (url, method, attempt)
        save_response   — HTTP status + response body received
        save_correlation— server-side correlation/trace id found
        save_error      — network/exception during save
    """

    CORRELATION_KEYS = (
        "x-request-id", "x-correlation-id", "x-trace-id",
        "requestid", "correlationid", "traceid", "reqid",
    )

    def __init__(self, max_body_chars: int = 500):
        self._records: list[SaveRecord] = []
        self._max_body = max_body_chars
        self._start = time.monotonic()
        self._current: Optional[SaveRecord] = None
        self._attempt = 0

    # -- lifecycle -----------------------------------------------------

    def begin(self, url: str = "", method: str = "POST") -> None:
        """Start tracking a new save attempt."""
        self._attempt += 1
        self._current = SaveRecord(attempt=self._attempt, url=url, method=method)
        self._start = time.monotonic()

    def record_http(self, status: int, body: str = "", url: str = "",
                    headers: Optional[dict] = None) -> SaveRecord:
        """Record the HTTP response of the save attempt."""
        rec = self._current or SaveRecord(attempt=self._attempt or 1)
        rec.status = status
        rec.response_body = (body or "")[: self._max_body]
        if url:
            rec.url = url
        rec.duration_ms = int((time.monotonic() - self._start) * 1000)

        # Extract server-side correlation id from headers/body
        if headers:
            for k, v in headers.items():
                if k.lower() in self.CORRELATION_KEYS and v:
                    rec.correlation_id = v
                    break
        if not rec.correlation_id:
            rec.correlation_id = self._find_correlation(body or "")

        self._records.append(rec)
        self._current = None
        return rec

    def record_exception(self, exc: Exception, url: str = "") -> SaveRecord:
        """Record a network/JS exception during save."""
        rec = self._current or SaveRecord(attempt=self._attempt or 1)
        rec.error = f"{type(exc).__name__}: {exc}"
        rec.duration_ms = int((time.monotonic() - self._start) * 1000)
        if url:
            rec.url = url
        self._records.append(rec)
        self._current = None
        return rec

    # -- output --------------------------------------------------------

    def events(self) -> list[TraceEvent]:
        """Convert all records to TraceEvents for the execution trace."""
        events: list[TraceEvent] = []
        for rec in self._records:
            events.append(TraceEvent(
                kind="save_request",
                target=rec.url or "save",
                status="ok" if rec.error is None else "failed",
                duration_ms=rec.duration_ms,
                detail=f"attempt={rec.attempt} method={rec.method}",
            ))
            if rec.status is not None:
                events.append(TraceEvent(
                    kind="save_response",
                    target=rec.url or "save",
                    status="ok" if 200 <= rec.status < 400 else "failed",
                    duration_ms=0,
                    detail=f"HTTP {rec.status} — {rec.response_body[:200]}",
                ))
            if rec.correlation_id:
                events.append(TraceEvent(
                    kind="save_correlation",
                    target=rec.correlation_id,
                    status="ok",
                    duration_ms=0,
                    detail="server-side correlation id",
                ))
            if rec.error:
                events.append(TraceEvent(
                    kind="save_error",
                    target=rec.url or "save",
                    status="failed",
                    duration_ms=rec.duration_ms,
                    detail=rec.error,
                ))
        return events

    @property
    def success(self) -> bool:
        """True if the latest attempt got a 2xx/3xx HTTP response."""
        if not self._records:
            return False
        last = self._records[-1]
        return last.error is None and last.status is not None and 200 <= last.status < 400

    def summary(self) -> str:
        if not self._records:
            return "SaveTracker: no attempts"
        last = self._records[-1]
        status = f"HTTP {last.status}" if last.status else "NETWORK ERROR"
        corr = f" corr={last.correlation_id}" if last.correlation_id else ""
        return f"SaveTracker: {status} in {last.duration_ms}ms{corr} ({len(self._records)} attempt(s))"

    def to_dict(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self._records]

    @staticmethod
    def _find_correlation(body: str) -> Optional[str]:
        """Best-effort: find a request/correlation id in the response body."""
        import re
        for key in ("requestId", "request_id", "correlationId", "traceId"):
            m = re.search(
                rf'"{key}"\s*:\s*"([^"]+)"', body, re.IGNORECASE
            )
            if m:
                return m.group(1)
        return None
