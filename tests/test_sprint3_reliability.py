"""Tests: Sprint 3 — Reliability & Observability.

Covers: RetryPolicy, TimeoutPolicy presets, overlay methods,
ActionTrace, RecoveryManager, and new exceptions.
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def _true() -> bool:
    return True


async def _false() -> bool:
    return False


# ══════════════════════════════════════════════════════════════════
# 1. New Exceptions (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestNewExceptions:
    """SessionExpired, NavigationFailed, UploadFailed, etc."""

    def test_session_expired(self):
        from src.browser.foundation import (
            SessionExpired, BrowserFoundationError,
        )
        e = SessionExpired("session gone")
        assert isinstance(e, BrowserFoundationError)
        assert "session" in str(e).lower()

    def test_navigation_failed(self):
        from src.browser.foundation import (
            NavigationFailed, BrowserFoundationError,
        )
        e = NavigationFailed("nav failed")
        assert isinstance(e, BrowserFoundationError)

    def test_upload_failed(self):
        from src.browser.foundation import (
            UploadFailed, BrowserFoundationError,
        )
        e = UploadFailed("upload fail")
        assert isinstance(e, BrowserFoundationError)

    def test_download_failed(self):
        from src.browser.foundation import (
            DownloadFailed, BrowserFoundationError,
        )
        e = DownloadFailed("dl fail")
        assert isinstance(e, BrowserFoundationError)

    def test_recovery_failed(self):
        from src.browser.foundation import (
            RecoveryFailed, BrowserFoundationError,
        )
        e = RecoveryFailed("recovery fail")
        assert isinstance(e, BrowserFoundationError)

    def test_all_exceptions_have_context_default(self):
        from src.browser.foundation import (
            SessionExpired, NavigationFailed, UploadFailed,
            DownloadFailed, RecoveryFailed,
        )
        for exc_cls in [SessionExpired, NavigationFailed,
                        UploadFailed, DownloadFailed, RecoveryFailed]:
            e = exc_cls("test")
            assert e.context == {}


# ══════════════════════════════════════════════════════════════════
# 2. TimeoutPolicy Presets (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestTimeoutPolicyPresets:
    """TimeoutPolicy.fast(), .normal(), .slow()."""

    def test_fast_preset(self):
        from src.browser.foundation import TimeoutPolicy
        t = TimeoutPolicy.fast()
        assert t.dom == 3.0
        assert t.network == 5.0
        assert t.click == 5.0
        assert t.navigation == 15.0
        assert t.short == 1.0

    def test_normal_preset(self):
        from src.browser.foundation import TimeoutPolicy
        t = TimeoutPolicy.standard()
        assert t.dom == 10.0
        assert t.network == 15.0
        assert t.short == 3.0

    def test_slow_preset(self):
        from src.browser.foundation import TimeoutPolicy
        t = TimeoutPolicy.slow()
        assert t.dom == 20.0
        assert t.network == 30.0
        assert t.click == 20.0
        assert t.navigation == 60.0
        assert t.short == 5.0
        assert t.upload == 180.0

    def test_presets_are_independent(self):
        from src.browser.foundation import TimeoutPolicy
        fast = TimeoutPolicy.fast()
        slow = TimeoutPolicy.slow()
        assert fast.dom != slow.dom
        assert fast.navigation != slow.navigation


# ══════════════════════════════════════════════════════════════════
# 3. RetryPolicy (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestRetryPolicy:
    """RetryPolicy dataclass and defaults."""

    def test_defaults(self):
        from src.browser.foundation import RetryPolicy
        p = RetryPolicy()
        assert p.retries == 3
        assert p.delay == 0.5
        assert p.backoff == 1.5
        assert p.jitter is False
        assert p.max_delay == 10.0

    def test_custom_values(self):
        from src.browser.foundation import RetryPolicy
        p = RetryPolicy(retries=5, delay=1.0, jitter=True)
        assert p.retries == 5
        assert p.delay == 1.0
        assert p.jitter is True

    def test_upload_policy(self):
        from src.browser.foundation import RetryPolicy
        p = RetryPolicy(retries=5, delay=2.0, backoff=2.0, max_delay=30.0)
        assert p.retries == 5
        assert p.max_delay == 30.0

    def test_click_policy_few_retries(self):
        from src.browser.foundation import RetryPolicy
        p = RetryPolicy(retries=2, delay=0.3, backoff=1.0)
        assert p.retries == 2


# ══════════════════════════════════════════════════════════════════
# 4. Overlay Methods (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestOverlayMethods:
    """dismiss_overlay, dismiss_modal, wait_overlay_disappear."""

    @pytest.mark.asyncio
    async def test_dismiss_overlay_when_none(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        b = BrowserFoundation(e)
        result = await b.dismiss_overlay(timeout=1.0)
        assert result is False  # No overlay to dismiss

    @pytest.mark.asyncio
    async def test_dismiss_overlay_when_visible(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        # Make an overlay visible with a close button
        e.visible_elements.add(".modal")
        e.visible_elements.add("button.close")
        e.click_ok = True
        b = BrowserFoundation(e)
        result = await b.dismiss_overlay(timeout=3.0)
        assert result is True

    @pytest.mark.asyncio
    async def test_dismiss_modal(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        b = BrowserFoundation(e)
        result = await b.dismiss_modal(timeout=1.0)
        # Should attempt Escape key and return True
        assert result is True

    @pytest.mark.asyncio
    async def test_wait_overlay_disappear_when_none(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        b = BrowserFoundation(e)
        # Should return immediately
        await b.wait_overlay_disappear(timeout=1.0)

    @pytest.mark.asyncio
    async def test_wait_overlay_disappear_when_visible(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("[role='dialog']")
        b = BrowserFoundation(e)
        # Should not timeout — just wait and return
        await b.wait_overlay_disappear(timeout=1.0)


# ══════════════════════════════════════════════════════════════════
# 5. ActionTrace (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestActionTrace:
    """ActionTrace — collector, context manager, formatting."""

    def test_trace_creates_empty(self):
        from src.browser.foundation import ActionTrace
        t = ActionTrace()
        assert len(t.entries) == 0
        assert t.enabled is True

    def test_trace_add_entry(self):
        from src.browser.foundation import ActionTrace, TraceEntry
        t = ActionTrace()
        t.add(TraceEntry(action="safe_click", selector="#btn", duration=0.5))
        assert len(t.entries) == 1
        assert t.entries[0].action == "safe_click"
        assert t.entries[0].elapsed_ms == 500

    def test_trace_disable(self):
        from src.browser.foundation import ActionTrace, TraceEntry
        t = ActionTrace()
        t.disable()
        t.add(TraceEntry(action="test"))
        assert len(t.entries) == 0  # Not recorded

    def test_trace_enable_after_disable(self):
        from src.browser.foundation import ActionTrace, TraceEntry
        t = ActionTrace()
        t.disable()
        t.enable()
        t.add(TraceEntry(action="test"))
        assert len(t.entries) == 1

    def test_trace_clear(self):
        from src.browser.foundation import ActionTrace, TraceEntry
        t = ActionTrace()
        t.add(TraceEntry(action="a"))
        t.add(TraceEntry(action="b"))
        t.clear()
        assert len(t.entries) == 0

    @pytest.mark.asyncio
    async def test_trace_context_manager_success(self):
        from src.browser.foundation import ActionTrace
        t = ActionTrace()
        async with t.record("safe_click", "#btn"):
            pass  # Success path
        assert len(t.entries) == 1
        entry = t.entries[0]
        assert entry.action == "safe_click"
        assert entry.selector == "#btn"
        assert entry.result == "ok"
        assert entry.duration > 0

    @pytest.mark.asyncio
    async def test_trace_context_manager_failure(self):
        from src.browser.foundation import ActionTrace
        t = ActionTrace()
        with pytest.raises(ValueError):
            async with t.record("safe_fill", "#input"):
                raise ValueError("fill failed")
        assert len(t.entries) == 1
        entry = t.entries[0]
        assert entry.result == "fail"
        assert "fill failed" in entry.error

    def test_trace_format(self):
        from src.browser.foundation import ActionTrace, TraceEntry
        t = ActionTrace()
        t.add(TraceEntry(action="click", selector="#a", duration=0.3))
        t.add(TraceEntry(action="fill", selector="#b", duration=0.5, retries=1))
        formatted = t.format()
        assert "Action Trace" in formatted
        assert "click" in formatted
        assert "#a" in formatted
        assert "retries=1" in formatted

    def test_trace_last_error_found(self):
        from src.browser.foundation import ActionTrace, TraceEntry
        t = ActionTrace()
        t.add(TraceEntry(action="ok"))
        t.add(TraceEntry(action="fail", result="fail", error="timeout"))
        assert t.last_error() == "timeout"

    def test_trace_last_error_none(self):
        from src.browser.foundation import ActionTrace
        t = ActionTrace()
        assert t.last_error() is None

    def test_trace_empty_format(self):
        from src.browser.foundation import ActionTrace
        t = ActionTrace()
        assert "(no trace entries)" in t.format()

    def test_trace_format_limit(self):
        from src.browser.foundation import ActionTrace, TraceEntry
        t = ActionTrace()
        for i in range(10):
            t.add(TraceEntry(action=f"op{i}"))
        formatted = t.format(limit=3)
        assert "op9" in formatted  # Last 3 entries
        assert "op0" not in formatted


# ══════════════════════════════════════════════════════════════════
# 6. RecoveryManager (6 tests)
# ══════════════════════════════════════════════════════════════════


async def _async_done() -> str:
    return "done"


async def _async_success() -> str:
    return "success"

class TestRecoveryManager:
    """execute_with_recovery, safe_execute, recovery pipeline."""

    @pytest.mark.asyncio
    async def test_execute_success_no_recovery_needed(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager

        b = BrowserFoundation(MockEngine())
        rm = RecoveryManager(
            browser=b,
            is_logged_in=_true,
        )

        result = await rm.execute_with_recovery(
            action=_async_done,
            max_recoveries=2,
        )
        assert result == "done"
        assert rm.stats["recoveries"] == 0

    @pytest.mark.asyncio
    async def test_execute_recovery_relogin(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager

        e = MockEngine()
        b = BrowserFoundation(e)
        relogin_called = [False]

        async def is_logged_in():
            return False  # Always needs login

        async def relogin():
            relogin_called[0] = True
            return True

        rm = RecoveryManager(
            browser=b,
            is_logged_in=is_logged_in,
            relogin=relogin,
        )

        call_count = [0]

        async def fails_then_works():
            call_count[0] += 1
            if call_count[0] <= 1:
                raise ValueError("transient error")
            return "done"

        result = await rm.execute_with_recovery(
            action=fails_then_works,
            max_recoveries=2,
        )
        assert result == "done"
        assert relogin_called[0] is True
        assert rm.stats["relogins"] == 1

    @pytest.mark.asyncio
    async def test_execute_recovery_exhausted(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager, RecoveryFailed

        e = MockEngine()
        b = BrowserFoundation(e)

        async def always_fails():
            raise ValueError("persistent")

        rm = RecoveryManager(
            browser=b,
            is_logged_in=_true,
        )

        with pytest.raises(RecoveryFailed):
            await rm.execute_with_recovery(
                action=always_fails,
                max_recoveries=1,
            )
        assert rm.stats["failed"] == 1

    @pytest.mark.asyncio
    async def test_safe_execute_returns_none_on_failure(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager

        e = MockEngine()
        b = BrowserFoundation(e)

        async def always_fails():
            raise ValueError("boom")

        rm = RecoveryManager(
            browser=b,
            is_logged_in=_true,
        )

        result = await rm.safe_execute(
            action=always_fails,
            max_recoveries=1,
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_safe_execute_returns_value_on_success(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager

        e = MockEngine()
        b = BrowserFoundation(e)

        rm = RecoveryManager(
            browser=b,
            is_logged_in=_true,
        )

        result = await rm.safe_execute(
            action=_async_success,
        )
        assert result == "success"

    @pytest.mark.asyncio
    async def test_recovery_pipeline_pdpa(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager

        e = MockEngine()
        e.url = "https://example.com/pdpa-terms"
        b = BrowserFoundation(e)
        pdpa_called = [False]

        async def accept_pdpa():
            pdpa_called[0] = True

        rm = RecoveryManager(
            browser=b,
            is_logged_in=_true,
            accept_pdpa=accept_pdpa,
        )

        call_count = [0]

        async def fails_once():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("transient")
            return "done"

        result = await rm.execute_with_recovery(
            action=fails_once,
            max_recoveries=2,
        )
        assert result == "done"
        assert pdpa_called[0] is True, "PDPA handler should have been called"

    @pytest.mark.asyncio
    async def test_recovery_stats(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager

        b = BrowserFoundation(MockEngine())
        rm = RecoveryManager(
            browser=b,
            is_logged_in=_true,
        )
        assert rm.stats["recoveries"] == 0
        assert rm.stats["relogins"] == 0
        assert rm.stats["failed"] == 0

    @pytest.mark.asyncio
    async def test_recovery_no_relogin_handler_raises_session_expired(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        from src.browser.recovery import RecoveryManager

        e = MockEngine()
        b = BrowserFoundation(e)

        rm = RecoveryManager(
            browser=b,
            is_logged_in=_false,  # Always logged out
            # No relogin handler
        )

        async def action():
            raise ValueError("any error")

        with pytest.raises(Exception):  # Should raise, not hang
            await rm.execute_with_recovery(
                action=action,
                max_recoveries=1,
            )
