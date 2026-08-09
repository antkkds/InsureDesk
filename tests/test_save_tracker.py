"""Tests for SaveTracker — save-failure observability into the trace.

Covers the ChatGPT review emphasis: connect Save → HTTP status →
response body → server-side correlation into the same TraceEvent stream
as field filling, so generic server errors are no longer black-box.
"""
from __future__ import annotations

from src.portal.execution.save_tracker import SaveTracker
from src.portal.execution.models import ExecutionResult


class TestSaveTracker:
    def test_successful_save_records_http(self):
        t = SaveTracker()
        t.begin("https://gears/saveQuote", method="POST")
        t.record_http(200, body="{\"status\":\"ok\"}", url="https://gears/saveQuote",
                      headers={"X-Request-Id": "req-abc123"})
        assert t.success is True
        events = t.events()
        kinds = [e.kind for e in events]
        assert "save_request" in kinds
        assert "save_response" in kinds
        assert "save_correlation" in kinds
        assert events[-1].target == "req-abc123"

    def test_failed_save_records_status_and_body(self):
        t = SaveTracker()
        t.begin("https://gears/saveQuote")
        t.record_http(500, body="{\"error\":\"generic server error\",\"requestId\":\"srv-42\"}")
        assert t.success is False
        events = t.events()
        resp = [e for e in events if e.kind == "save_response"][0]
        assert resp.status == "failed"
        assert "HTTP 500" in resp.detail
        # correlation found from body
        corr = [e for e in events if e.kind == "save_correlation"]
        assert corr and corr[0].target == "srv-42"

    def test_network_exception_records_error(self):
        t = SaveTracker()
        t.begin("https://gears/saveQuote")
        t.record_exception(TimeoutError("request timed out"))
        assert t.success is False
        events = t.events()
        errs = [e for e in events if e.kind == "save_error"]
        assert errs and "TimeoutError" in errs[0].detail

    def test_redirect_status_is_success(self):
        """302 (save accepted + redirect) counts as success — matches GEGLink."""
        t = SaveTracker()
        t.begin("https://gears/saveQuote")
        t.record_http(302, body="")
        assert t.success is True

    def test_multiple_attempts_accumulate(self):
        t = SaveTracker()
        t.begin("https://gears/saveQuote")
        t.record_http(500, body="first fail")
        t.begin("https://gears/saveQuote")
        t.record_http(200, body="second ok")
        assert len(t.to_dict()) == 2
        assert t.summary().startswith("SaveTracker: HTTP 200")

    def test_no_attempts(self):
        t = SaveTracker()
        assert t.success is False
        assert t.summary() == "SaveTracker: no attempts"

    def test_execution_result_trace_integration(self):
        """SaveTracker events merge into ExecutionResult.trace."""
        t = SaveTracker()
        t.begin("https://gears/saveQuote")
        t.record_http(500, body="{\"requestId\":\"x1\"}")

        result = ExecutionResult(success=False)
        result.trace.extend(t.events())
        d = result.to_dict()
        assert len(d["trace"]) >= 3
        assert any(e["kind"] == "save_response" for e in d["trace"])
        assert any(e["kind"] == "save_correlation" for e in d["trace"])
