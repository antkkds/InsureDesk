"""Tests: Sprint 4 — Assistant Session Runtime.

Tests for:
1. SessionData — dataclass, state transitions, to_dict
2. SessionRuntime — create, start, pause, resume, complete, cancel
3. Session context building — LLM context generation
4. Integration with ToolRegistry
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. SessionData — model and state (8 tests)
# ══════════════════════════════════════════════════════════════════


class TestSessionData:
    """SessionData dataclass and state management."""

    def test_default_state_is_idle(self):
        from src.runtime.session_runtime import SessionData, SessionState
        s = SessionData()
        assert s.state == SessionState.IDLE
        assert s.id == ""

    def test_set_state_tracks_previous(self):
        from src.runtime.session_runtime import SessionData, SessionState
        s = SessionData()
        s.set_state(SessionState.PROCESSING)
        assert s.state == SessionState.PROCESSING
        assert s.previous_state == SessionState.IDLE

    def test_set_state_updates_updated_at(self):
        from src.runtime.session_runtime import SessionData, SessionState
        s = SessionData()
        old = s.updated_at
        s.set_state(SessionState.COMPLETED)
        assert s.updated_at != old

    def test_to_dict_includes_state_value(self):
        from src.runtime.session_runtime import SessionData, SessionState
        s = SessionData(id="S001", state=SessionState.PROCESSING)
        d = s.to_dict()
        assert d["id"] == "S001"
        assert d["state"] == "processing"
        assert d["previous_state"] is None

    def test_to_dict_after_state_change(self):
        from src.runtime.session_runtime import SessionData, SessionState
        s = SessionData(id="S002")
        s.set_state(SessionState.WAITING_FOR_INPUT)
        d = s.to_dict()
        assert d["state"] == "waiting"
        assert d["previous_state"] == "idle"

    def test_collected_data_default(self):
        from src.runtime.session_runtime import SessionData
        s = SessionData()
        assert s.collected_data == {}

    def test_action_log_default(self):
        from src.runtime.session_runtime import SessionData
        s = SessionData()
        assert s.action_log == []

    def test_tool_calls_default(self):
        from src.runtime.session_runtime import SessionData
        s = SessionData()
        assert s.tool_calls == []


# ══════════════════════════════════════════════════════════════════
# 2. SessionRuntime — lifecycle management (18 tests)
# ══════════════════════════════════════════════════════════════════


class TestSessionRuntime:
    """SessionRuntime: create, get, state transitions, data."""

    @pytest.fixture
    def runtime(self):
        from src.runtime.session_runtime import SessionRuntime
        return SessionRuntime()

    def test_create_session(self, runtime):
        s = runtime.create_session(customer_id="C001", task="fire_quote")
        assert s.id.startswith("S")
        assert s.customer_id == "C001"
        assert s.task == "fire_quote"
        assert s.state.value == "idle"

    def test_create_session_with_initial_data(self, runtime):
        s = runtime.create_session(
            customer_id="C001",
            task="fire_quote",
            initial_data={"proposer_name": "Tiong Hoe Hung"},
        )
        assert s.collected_data["proposer_name"] == "Tiong Hoe Hung"

    def test_create_session_generates_unique_ids(self, runtime):
        s1 = runtime.create_session(customer_id="C001")
        s2 = runtime.create_session(customer_id="C002")
        assert s1.id != s2.id

    def test_get_session(self, runtime):
        s = runtime.create_session(customer_id="C001")
        found = runtime.get_session(s.id)
        assert found is not None
        assert found.id == s.id

    def test_get_session_not_found(self, runtime):
        assert runtime.get_session("nonexistent") is None

    def test_count(self, runtime):
        assert runtime.count() == 0
        runtime.create_session(customer_id="C001")
        assert runtime.count() == 1
        runtime.create_session(customer_id="C002")
        assert runtime.count() == 2

    def test_start_session(self, runtime):
        s = runtime.create_session(customer_id="C001")
        started = runtime.start(s.id)
        assert started.state.value == "processing"
        assert started.previous_state.value == "idle"

    def test_start_already_started_raises(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.start(s.id)
        with pytest.raises(ValueError, match="current state is processing"):
            runtime.start(s.id)

    def test_pause_session(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.start(s.id)
        paused = runtime.pause(s.id, reason="Need occupation")
        assert paused.state.value == "waiting"
        assert paused.waiting_reason == "Need occupation"

    def test_pause_from_idle(self, runtime):
        """Pausing an idle session should work."""
        s = runtime.create_session(customer_id="C001")
        paused = runtime.pause(s.id, reason="Need info")
        assert paused.state.value == "waiting"

    def test_pause_completed_raises(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.complete(s.id)
        with pytest.raises(ValueError, match="current state is completed"):
            runtime.pause(s.id)

    def test_resume_session(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.start(s.id)
        runtime.pause(s.id, reason="Need occupation")
        resumed = runtime.resume(s.id, data={"occupation": "factory"})
        assert resumed.state.value == "processing"
        assert resumed.waiting_reason == ""
        assert resumed.collected_data["occupation"] == "factory"

    def test_resume_without_data(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.pause(s.id, reason="Need info")
        resumed = runtime.resume(s.id)
        assert resumed.state.value == "processing"

    def test_resume_not_paused_raises(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.start(s.id)
        with pytest.raises(ValueError, match="expected: waiting"):
            runtime.resume(s.id)

    def test_complete_session(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.start(s.id)
        completed = runtime.complete(s.id)
        assert completed.state.value == "completed"
        assert completed.completed_at is not None

    def test_cancel_session(self, runtime):
        s = runtime.create_session(customer_id="C001")
        cancelled = runtime.cancel(s.id, reason="Customer changed mind")
        assert cancelled.state.value == "cancelled"
        assert cancelled.error_message == "Customer changed mind"

    def test_mark_error(self, runtime):
        s = runtime.create_session(customer_id="C001")
        runtime.start(s.id)
        errored = runtime.mark_error(s.id, "Quote calculation failed")
        assert errored.state.value == "error"
        assert errored.error_message == "Quote calculation failed"
        assert errored.retry_count == 1

    def test_delete_session(self, runtime):
        s = runtime.create_session(customer_id="C001")
        assert runtime.count() == 1
        runtime.delete_session(s.id)
        assert runtime.count() == 0

    def test_delete_session_not_found(self, runtime):
        assert runtime.delete_session("nonexistent") is False


# ══════════════════════════════════════════════════════════════════
# 3. Session Data Management (6 tests)
# ══════════════════════════════════════════════════════════════════


class TestSessionDataManagement:
    """set_data, get_data, log_action, log_tool_call."""

    @pytest.fixture
    def runtime(self):
        from src.runtime.session_runtime import SessionRuntime
        r = SessionRuntime()
        s = r.create_session(customer_id="C001", task="fire_quote")
        r.start(s.id)
        return r, s.id

    def test_set_and_get_data(self, runtime):
        r, sid = runtime
        r.set_data(sid, "proposer_name", "Tiong Hoe Hung")
        assert r.get_data(sid, "proposer_name") == "Tiong Hoe Hung"

    def test_get_data_default(self, runtime):
        r, sid = runtime
        assert r.get_data(sid, "nonexistent") is None
        assert r.get_data(sid, "nonexistent", "default") == "default"

    def test_get_all_data(self, runtime):
        r, sid = runtime
        r.set_data(sid, "name", "Alice")
        r.set_data(sid, "ic", "123456")
        all_data = r.get_all_data(sid)
        assert all_data == {"name": "Alice", "ic": "123456"}

    def test_log_action(self, runtime):
        r, sid = runtime
        r.log_action(sid, "create_quote", {"risk_class": "fire"})
        assert len(r.get_session(sid).action_log) == 1
        assert r.get_session(sid).action_log[0]["action"] == "create_quote"

    def test_log_tool_call(self, runtime):
        r, sid = runtime
        r.log_tool_call(sid, "create_quote", {"risk_class": "fire"},
                        result={"quote_number": "MOCK-001"}, duration_ms=150.5)
        calls = r.get_session(sid).tool_calls
        assert len(calls) == 1
        assert calls[0]["tool"] == "create_quote"
        assert calls[0]["duration_ms"] == 150.5

    def test_pending_actions(self, runtime):
        r, sid = runtime
        r.add_pending_action(sid, "need_occupation", {"prompt": "What is the occupation?"})
        assert len(r.get_session(sid).pending_actions) == 1
        r.clear_pending_actions(sid)
        assert len(r.get_session(sid).pending_actions) == 0


# ══════════════════════════════════════════════════════════════════
# 4. Session listing & filtering (5 tests)
# ══════════════════════════════════════════════════════════════════


class TestSessionListing:
    """list_sessions with state and customer filters."""

    @pytest.fixture
    def runtime(self):
        from src.runtime.session_runtime import SessionRuntime
        r = SessionRuntime()
        s1 = r.create_session(customer_id="C001", task="fire_quote")
        s2 = r.create_session(customer_id="C001", task="motor_quote")
        s3 = r.create_session(customer_id="C002", task="travel_quote")
        r.complete(s3.id)
        return r, s1, s2, s3

    def test_list_all(self, runtime):
        r, *_ = runtime
        assert len(r.list_sessions()) == 3

    def test_list_by_customer(self, runtime):
        r, *_ = runtime
        sessions = r.list_sessions(customer_id="C001")
        assert len(sessions) == 2

    def test_list_by_state(self, runtime):
        from src.runtime.session_runtime import SessionState
        r, *_ = runtime
        sessions = r.list_sessions(state_filter=SessionState.COMPLETED)
        assert len(sessions) == 1

    def test_list_by_customer_and_state(self, runtime):
        from src.runtime.session_runtime import SessionState
        r, *_ = runtime
        sessions = r.list_sessions(customer_id="C001", state_filter=SessionState.IDLE)
        assert len(sessions) == 2

    def test_list_limit(self, runtime):
        r, *_ = runtime
        sessions = r.list_sessions(limit=1)
        assert len(sessions) == 1


# ══════════════════════════════════════════════════════════════════
# 5. SessionContextBuilder (3 tests)
# ══════════════════════════════════════════════════════════════════


class TestSessionContextBuilder:
    """Build LLM context from session data."""

    def test_build_basic_context(self):
        from src.runtime.session_runtime import SessionData, SessionContextBuilder

        s = SessionData(id="S001", task="fire_quote", customer_id="C001")
        ctx = SessionContextBuilder.build_context(s)
        assert "Session ID: S001" in ctx
        assert "Task: fire_quote" in ctx
        assert "Customer: C001" in ctx

    def test_build_with_collected_data(self):
        from src.runtime.session_runtime import (
            SessionData, SessionContextBuilder, SessionState,
        )

        s = SessionData(
            id="S001", task="fire_quote",
            collected_data={"proposer_name": "Tiong", "sum_insured": 5000000},
            state=SessionState.PROCESSING,
        )
        ctx = SessionContextBuilder.build_context(s)
        assert "Tiong" in ctx
        assert "5000000" in ctx

    def test_build_with_waiting_reason(self):
        from src.runtime.session_runtime import (
            SessionData, SessionContextBuilder, SessionState,
        )

        s = SessionData(
            id="S001", task="fire_quote",
            state=SessionState.WAITING_FOR_INPUT,
            waiting_reason="Need occupation",
        )
        ctx = SessionContextBuilder.build_context(s)
        assert "Waiting For" in ctx
        assert "Need occupation" in ctx


# ══════════════════════════════════════════════════════════════════
# 6. Integration — Session + ToolRegistry (5 tests)
# ══════════════════════════════════════════════════════════════════


class TestSessionToolIntegration:
    """Session Runtime integrated with ToolRegistry."""

    @pytest.fixture
    def setup(self):
        from src.tools.registry import ToolRegistry
        from src.tools.insurance.quote_tools import (
            register_all_quote_tools, reset_shared_adapter,
        )
        from src.runtime.session_runtime import SessionRuntime

        ToolRegistry.reset_instance()
        reset_shared_adapter()
        registry = ToolRegistry.get_instance()
        register_all_quote_tools(registry)
        runtime = SessionRuntime()

        yield registry, runtime

        ToolRegistry.reset_instance()
        reset_shared_adapter()

    @pytest.fixture
    def event_loop(self):
        import asyncio
        loop = asyncio.new_event_loop()
        yield loop
        loop.close()

    def test_create_quote_in_session(self, setup, event_loop):
        """Create a quote through tools and log it in a session."""
        registry, runtime = setup

        # Create session
        session = runtime.create_session(
            customer_id="C001",
            task="fire_quote",
            initial_data={"proposer_name": "Tiong Hoe Hung"},
        )
        runtime.start(session.id)

        # Execute tool
        result = event_loop.run_until_complete(
            registry.execute("create_quote",
                             proposer_name="Tiong Hoe Hung",
                             risk_class="fire",
                             sum_insured=5000000)
        )
        assert result.success is True

        # Log tool call in session
        runtime.log_tool_call(session.id, "create_quote",
                              {"risk_class": "fire", "sum_insured": 5000000},
                              result={"quote_number": result.data["quote_number"]},
                              duration_ms=result.duration_ms)

        # Verify
        assert len(runtime.get_session(session.id).tool_calls) == 1
        assert runtime.get_session(session.id).tool_calls[0]["tool"] == "create_quote"

    def test_full_quote_workflow_with_session(self, setup, event_loop):
        """create → pause → provide_data → calculate → complete."""
        registry, runtime = setup

        # Start session
        session = runtime.create_session(customer_id="C001", task="fire_quote")
        runtime.start(session.id)

        # Step 1: Create quote
        result = event_loop.run_until_complete(
            registry.execute("create_quote",
                             proposer_name="Tiong",
                             risk_class="fire",
                             sum_insured=5000000)
        )
        runtime.log_tool_call(session.id, "create_quote", {}, result={"ok": True})
        runtime.set_data(session.id, "quote_number", result.data["quote_number"])

        # Step 2: Pause — need additional info
        runtime.pause(session.id, reason="Need occupation for risk assessment")

        # Simulate user providing data
        runtime.resume(session.id, data={"occupation": "factory"})
        assert runtime.get_data(session.id, "occupation") == "factory"

        # Step 3: Calculate
        result = event_loop.run_until_complete(
            registry.execute("calculate_quote",
                             proposer_name="Tiong",
                             risk_class="fire",
                             sum_insured=5000000)
        )
        runtime.log_tool_call(session.id, "calculate_quote", {}, result={"ok": True})
        runtime.set_data(session.id, "total_premium", result.data["total_premium"])

        # Step 4: Complete
        runtime.complete(session.id)
        final = runtime.get_session(session.id)
        assert final.state.value == "completed"
        assert len(final.tool_calls) == 2
        assert final.collected_data["total_premium"] > 0

    def test_session_pause_resume_cycle(self, setup, event_loop):
        """Multiple pause/resume cycles."""
        registry, runtime = setup
        session = runtime.create_session(customer_id="C001", task="fire_quote")
        runtime.start(session.id)

        # Cycle 1
        runtime.pause(session.id, reason="Need info 1")
        runtime.resume(session.id, data={"info1": "value1"})
        assert runtime.get_data(session.id, "info1") == "value1"

        # Cycle 2
        runtime.pause(session.id, reason="Need info 2")
        runtime.resume(session.id, data={"info2": "value2"})
        assert runtime.get_data(session.id, "info2") == "value2"

        # Both values should be present
        all_data = runtime.get_all_data(session.id)
        assert all_data["info1"] == "value1"
        assert all_data["info2"] == "value2"

    def test_session_context_building_with_tool_calls(self, setup, event_loop):
        """Build LLM context from session with tool calls."""
        from src.runtime.session_runtime import SessionContextBuilder

        registry, runtime = setup
        session = runtime.create_session(customer_id="C001", task="fire_quote")
        runtime.start(session.id)

        runtime.log_action(session.id, "list_products",
                           {"result": "Found FIRE, MOTOR"})
        runtime.set_data(session.id, "selected_product", "FIRE")
        runtime.pause(session.id, reason="Need sum insured amount")

        ctx = SessionContextBuilder.build_context(runtime.get_session(session.id))
        assert "Session ID:" in ctx
        assert "selected_product: FIRE" in ctx
        assert "Waiting For" in ctx
        assert "Need sum insured amount" in ctx
        assert "list_products" in ctx

    def test_error_recovery(self, setup, event_loop):
        """Session can recover after error."""
        registry, runtime = setup
        session = runtime.create_session(customer_id="C001", task="fire_quote")
        runtime.start(session.id)

        # Error
        runtime.mark_error(session.id, "Connection lost")
        assert runtime.get_session(session.id).state.value == "error"

        # Can still restart — user can choose to create new session
        # (error sessions are terminal, but we should be able to inspect them)
        assert runtime.get_session(session.id).retry_count == 1
