"""
Phase 4.6 tests — E2E profile enforcement + execution trace.

ChatGPT Phase 4.6 guard:
    Real E2E Test Profile — do not rely on a human remembering
    "no Save Draft, no Submit". Load + enforce at startup.
"""

import json

import pytest

from src.agent import (
    DEFAULT_PROFILE,
    E2EBlockedError,
    E2EProfile,
    E2EProfileEnforcer,
    ExecutionTracer,
)


class TestE2EProfile:
    def test_default_profile_blocks_submit(self):
        profile = E2EProfile.from_dict(None)
        assert profile.name == "real_validation"
        assert profile.mode == "real"
        assert profile.permission == "readonly"
        assert profile.is_action_allowed("insurance.quote.calculate")
        assert not profile.is_action_allowed("insurance.quote.save_draft")
        assert not profile.is_action_allowed("insurance.policy.submit")

    def test_blocks_mutating_argument(self):
        profile = E2EProfile.from_dict(None)
        assert not profile.is_action_allowed(
            "insurance.quote.calculate", {"action": "submit"}
        )

    def test_custom_profile(self):
        profile = E2EProfile.from_dict(
            {
                "name": "custom",
                "execution_policy": {"mode": "real", "permission": "readonly"},
                "blocked": ["submit", "delete"],
            }
        )
        assert profile.is_action_allowed("insurance.quote.calculate")
        assert not profile.is_action_allowed("insurance.policy.submit")

    def test_enforcer_raises_blocked(self):
        enforcer = E2EProfileEnforcer()
        with pytest.raises(E2EBlockedError) as exc_info:
            enforcer.check("insurance.policy.submit")
        assert exc_info.value.error_code == "READ_ONLY_BLOCKED"
        assert enforcer.blocks == 1

    def test_enforcer_allows_quote(self):
        enforcer = E2EProfileEnforcer()
        enforcer.check("insurance.quote.calculate")  # no raise
        assert enforcer.blocks == 0


class TestExecutionTracer:
    def test_log_and_read(self, tmp_path):
        tracer = ExecutionTracer(trace_dir=str(tmp_path))
        tracer.log("exec_1", "agent_received", {"capability": "insurance.quote.calculate"})
        tracer.log("exec_1", "execution_started")
        tracer.log("exec_1", "result_reported", {"status": "success"})
        events = tracer.read("exec_1")
        assert len(events) == 3
        assert events[0]["stage"] == "agent_received"
        assert events[0]["detail"]["capability"] == "insurance.quote.calculate"

    def test_timeline_format(self, tmp_path):
        tracer = ExecutionTracer(trace_dir=str(tmp_path))
        tracer.log("exec_2", "agent_received")
        tracer.log("exec_2", "quote_calculated")
        timeline = tracer.format_timeline("exec_2")
        assert "Execution: exec_2" in timeline
        assert "agent_received" in timeline
        assert "quote_calculated" in timeline

    def test_read_missing_returns_empty(self, tmp_path):
        tracer = ExecutionTracer(trace_dir=str(tmp_path))
        assert tracer.read("ghost") == []

    def test_never_raises_on_bad_dir(self):
        tracer = ExecutionTracer(trace_dir="/proc/nonexistent/x")
        tracer.log("exec_3", "stage")  # must not raise
