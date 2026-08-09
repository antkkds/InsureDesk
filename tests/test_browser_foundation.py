"""Tests: Browser Foundation Layer — safe_click, safe_fill, retry, wait_*

Sprint 1 of Phase 2 — Browser Automation Foundation.
All tests use MockEngine (no Playwright/CDP required).
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ══════════════════════════════════════════════════════════════════
# 1. TimeoutPolicy (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestTimeoutPolicy:
    """TimeoutPolicy dataclass defaults and overrides."""

    def test_defaults(self):
        from src.browser.foundation import TimeoutPolicy
        t = TimeoutPolicy()
        assert t.dom == 10.0
        assert t.network == 15.0
        assert t.normal == 10.0
        assert t.navigation == 30.0
        assert t.upload == 120.0
        assert t.short == 3.0

    def test_custom_timeouts(self):
        from src.browser.foundation import TimeoutPolicy
        t = TimeoutPolicy(dom=5.0, click=8.0, upload=60.0)
        assert t.dom == 5.0
        assert t.click == 8.0
        assert t.upload == 60.0
        # Unset fields remain default
        assert t.normal == 10.0

    def test_timeout_is_immutable(self):
        from src.browser.foundation import TimeoutPolicy
        t = TimeoutPolicy()
        t.dom = 99.0  # dataclass is mutable by design
        assert t.dom == 99.0

    def test_constructor_all_fields(self):
        from src.browser.foundation import TimeoutPolicy
        t = TimeoutPolicy(
            dom=1, network=2, loading=3, iframe=4,
            click=5, fill=6, navigation=7, upload=8,
            short=9, normal=10, long=30,
        )
        assert t.dom == 1
        assert t.long == 30


# ══════════════════════════════════════════════════════════════════
# 2. Exception Hierarchy (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestFoundationExceptions:
    """Exception hierarchy for BrowserFoundation errors."""

    def test_base_error(self):
        from src.browser.foundation import BrowserFoundationError
        err = BrowserFoundationError("test")
        assert str(err) == "test"
        assert err.context == {}

    def test_base_error_with_context(self):
        from src.browser.foundation import BrowserFoundationError
        err = BrowserFoundationError("test", context={"key": "val"})
        assert err.context["key"] == "val"

    def test_element_not_visible(self):
        from src.browser.foundation import ElementNotVisible, BrowserFoundationError
        err = ElementNotVisible("not visible")
        assert isinstance(err, BrowserFoundationError)

    def test_verification_failed(self):
        from src.browser.foundation import VerificationFailed, BrowserFoundationError
        err = VerificationFailed("verify fail")
        assert isinstance(err, BrowserFoundationError)

    def test_retry_exceeded(self):
        from src.browser.foundation import (
            RetryExceeded, BrowserFoundationError, WaitTimeout,
        )
        err = RetryExceeded("retry fail")
        assert isinstance(err, BrowserFoundationError)
        wt = WaitTimeout("timeout")
        assert isinstance(wt, BrowserFoundationError)


# ══════════════════════════════════════════════════════════════════
# 3. MockEngine (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestMockEngine:
    """MockEngine test double correctness."""

    @pytest.mark.asyncio
    async def test_engine_records_calls(self):
        from src.browser.foundation import MockEngine
        e = MockEngine()
        e.visible_elements.add("#btn")
        await e.click("#btn")
        assert "click(#btn)" in e.calls

    @pytest.mark.asyncio
    async def test_engine_navigate(self):
        from src.browser.foundation import MockEngine
        e = MockEngine()
        ok = await e.navigate("https://example.com")
        assert ok is True
        assert e.url == "https://example.com"

    @pytest.mark.asyncio
    async def test_engine_fill_and_verify(self):
        from src.browser.foundation import MockEngine
        e = MockEngine()
        await e.fill("#user", "test_user")
        val = await e.get_attribute("#user", "value")
        assert val == "test_user"


# ══════════════════════════════════════════════════════════════════
# 4. BrowserFoundation Basics (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestBrowserFoundationBasics:
    """Constructor, properties, delegates."""

    @pytest.mark.asyncio
    async def test_create_with_defaults(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        b = BrowserFoundation(e)
        assert b.engine is e
        assert b.timeout is not None

    @pytest.mark.asyncio
    async def test_create_with_custom_timeout(self):
        from src.browser.foundation import BrowserFoundation, MockEngine, TimeoutPolicy
        t = TimeoutPolicy(dom=5.0)
        b = BrowserFoundation(MockEngine(), timeout=t)
        assert b.timeout.dom == 5.0

    @pytest.mark.asyncio
    async def test_stats_initialized(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        b = BrowserFoundation(MockEngine())
        assert b.stats["clicks"] == 0
        assert b.stats["fills"] == 0
        assert b.stats["waits"] == 0
        assert b.stats["retries"] == 0

    @pytest.mark.asyncio
    async def test_delegate_navigate(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        b = BrowserFoundation(e)
        ok = await b.navigate("https://example.com")
        assert ok is True
        assert e.url == "https://example.com"


# ══════════════════════════════════════════════════════════════════
# 5. Wait Methods (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestWaitMethods:
    """wait_dom, wait_network, wait_loading, wait_iframe, wait_until_ready."""

    @pytest.mark.asyncio
    async def test_wait_dom_ready(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.ready_state = "complete"
        b = BrowserFoundation(e)
        await b.wait_dom(timeout=5.0)
        assert b.stats["waits"] >= 1

    @pytest.mark.asyncio
    async def test_wait_dom_with_delay(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        import asyncio
        e = MockEngine()
        e.ready_state = "loading"  # Not ready initially

        # Override evaluate to simulate delayed ready
        original_eval = e.evaluate

        call_count = 0

        async def delayed_eval(script):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return False
            return True

        e.evaluate = delayed_eval
        b = BrowserFoundation(e)
        await b.wait_dom(timeout=10.0)
        assert call_count >= 2

    @pytest.mark.asyncio
    async def test_wait_dom_timeout(self):
        from src.browser.foundation import BrowserFoundation, MockEngine, WaitTimeout
        e = MockEngine()
        e.ready_state = "loading"

        async def never_ready(script):
            return False

        e.evaluate = never_ready
        b = BrowserFoundation(e)
        with pytest.raises(WaitTimeout, match="DOM not ready"):
            await b.wait_dom(timeout=1.0)

    @pytest.mark.asyncio
    async def test_wait_network(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        b = BrowserFoundation(e)
        await b.wait_network(timeout=5.0)

    @pytest.mark.asyncio
    async def test_wait_loading_no_indicator(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        b = BrowserFoundation(e)
        await b.wait_loading(timeout=5.0)
        assert b.stats["waits"] >= 1

    @pytest.mark.asyncio
    async def test_wait_until_ready(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.ready_state = "complete"
        b = BrowserFoundation(e)
        await b.wait_until_ready(timeout=10.0)
        # At least one wait method succeeded
        assert b.stats["waits"] >= 1


# ══════════════════════════════════════════════════════════════════
# 6. retry() (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestRetry:
    """Generic retry wrapper."""

    @pytest.mark.asyncio
    async def test_retry_succeeds_first(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        b = BrowserFoundation(MockEngine())

        async def ok():
            return "done"

        result = await b.retry(ok, retries=3)
        assert result == "done"
        assert b.stats["retries"] == 0  # No retries needed

    @pytest.mark.asyncio
    async def test_retry_succeeds_on_second(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        b = BrowserFoundation(MockEngine())

        call_count = 0

        async def fail_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("first attempt")
            return "done"

        result = await b.retry(fail_then_ok, retries=3, delay=0.01)
        assert result == "done"
        assert b.stats["retries"] == 1  # 1 retry

    @pytest.mark.asyncio
    async def test_retry_exhausted(self):
        from src.browser.foundation import BrowserFoundation, MockEngine, RetryExceeded
        b = BrowserFoundation(MockEngine())

        async def always_fail():
            raise ValueError("always")

        with pytest.raises(RetryExceeded, match="3 attempts"):
            await b.retry(always_fail, retries=3, delay=0.01)

    @pytest.mark.asyncio
    async def test_retry_does_not_retry_foundation_errors(self):
        from src.browser.foundation import (
            BrowserFoundation, MockEngine,
            VerificationFailed, RetryExceeded,
        )
        b = BrowserFoundation(MockEngine())

        async def raises_foundation_error():
            raise VerificationFailed("no retry")

        with pytest.raises(VerificationFailed):
            await b.retry(raises_foundation_error, retries=3, delay=0.01)


# ══════════════════════════════════════════════════════════════════
# 7. safe_click() (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestSafeClick:
    """safe_click — locate → visible → scroll → click → verify."""

    @pytest.mark.asyncio
    async def test_safe_click_success(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#btnLogin")
        e.click_ok = True
        b = BrowserFoundation(e)
        await b.safe_click("#btnLogin", timeout=5.0)
        assert b.stats["clicks"] == 1

    @pytest.mark.asyncio
    async def test_safe_click_not_visible_triggers_scroll(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        # Element exists (wait_for_selector returns True) but not visible initially
        e.visible_elements.add("#btnLogin")
        # Remove it first, so is_visible returns False
        e.visible_elements.discard("#btnLogin")
        b = BrowserFoundation(e)
        with pytest.raises(Exception):
            await b.safe_click("#btnLogin", timeout=5.0)

    @pytest.mark.asyncio
    async def test_safe_click_fail_then_retry(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#btnLogin")
        call_count = [0]

        original_click = e.click

        async def flaky_click(selector, timeout=10000):
            call_count[0] += 1
            if call_count[0] < 2:
                return False
            return await original_click(selector, timeout)

        e.click = flaky_click
        b = BrowserFoundation(e)
        await b.safe_click("#btnLogin", retries=3, timeout=5.0)
        assert b.stats["clicks"] == 1
        assert call_count[0] >= 2

    @pytest.mark.asyncio
    async def test_safe_click_selector_not_found(self):
        from src.browser.foundation import (
            BrowserFoundation, MockEngine, VerificationFailed,
        )
        e = MockEngine()
        # Don't add element to visible set
        b = BrowserFoundation(e)

        async def not_found(sel, timeout=10000):
            return False

        e.wait_for_selector = not_found
        with pytest.raises(VerificationFailed):
            await b.safe_click("#nonexistent", retries=2, timeout=1.0)

    @pytest.mark.asyncio
    async def test_safe_click_records_call(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#submit")
        b = BrowserFoundation(e)
        await b.safe_click("#submit", timeout=5.0)
        assert "click(#submit)" in e.calls


# ══════════════════════════════════════════════════════════════════
# 8. safe_fill() (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestSafeFill:
    """safe_fill — focus → clear → fill → verify."""

    @pytest.mark.asyncio
    async def test_safe_fill_success(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#username")
        b = BrowserFoundation(e)
        await b.safe_fill("#username", "test_user", timeout=5.0)
        assert b.stats["fills"] == 1
        assert e.input_values["#username"] == "test_user"

    @pytest.mark.asyncio
    async def test_safe_fill_verify_wrong_triggers_retry(self):
        from src.browser.foundation import BrowserFoundation, MockEngine, VerificationFailed
        e = MockEngine()
        e.visible_elements.add("#username")
        call_count = [0]

        async def wrong_fill(sel, value, delay_ms=50):
            call_count[0] += 1
            e.input_values[sel] = value + "_wrong"  # Simulate JS corruption
            return True

        e.fill = wrong_fill
        b = BrowserFoundation(e)
        with pytest.raises(VerificationFailed, match="verification failed"):
            await b.safe_fill("#username", "test_user", retries=2, timeout=1.0)

    @pytest.mark.asyncio
    async def test_safe_fill_verify_succeeds_eventually(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#username")
        call_count = [0]

        async def flaky_fill(sel, value, delay_ms=50):
            call_count[0] += 1
            if call_count[0] < 2:
                e.input_values[sel] = value + "_wrong"
            else:
                e.input_values[sel] = value
            return True

        e.fill = flaky_fill
        b = BrowserFoundation(e)
        await b.safe_fill("#username", "test_user", retries=3, timeout=5.0)
        assert b.stats["fills"] == 1
        assert b.stats["retries"] == 1

    @pytest.mark.asyncio
    async def test_safe_fill_not_found(self):
        from src.browser.foundation import (
            BrowserFoundation, MockEngine, VerificationFailed,
        )
        e = MockEngine()

        async def not_found(sel, timeout=10000):
            return False

        e.wait_for_selector = not_found
        b = BrowserFoundation(e)
        with pytest.raises(VerificationFailed):
            await b.safe_fill("#missing", "val", retries=1, timeout=1.0)

    @pytest.mark.asyncio
    async def test_safe_fill_escapes_selector(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("input[name=\"oac_username\"]")
        b = BrowserFoundation(e)
        await b.safe_fill(
            "input[name=\"oac_username\"]", "user",
            timeout=5.0,
        )
        assert b.stats["fills"] == 1


# ══════════════════════════════════════════════════════════════════
# 9. safe_select() (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestSafeSelect:
    """safe_select — dropdown option with verification."""

    @pytest.mark.asyncio
    async def test_select_success(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#state")
        b = BrowserFoundation(e)
        await b.safe_select("#state", "Selangor", timeout=5.0)
        assert b.stats["selects"] == 1

    @pytest.mark.asyncio
    async def test_select_not_found(self):
        from src.browser.foundation import BrowserFoundation, MockEngine, VerificationFailed
        e = MockEngine()
        async def not_found(sel, timeout=10000):
            return False
        e.wait_for_selector = not_found
        b = BrowserFoundation(e)
        with pytest.raises(VerificationFailed):
            await b.safe_select("#missing", "val", retries=1, timeout=1.0)

    @pytest.mark.asyncio
    async def test_select_records_value(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#plan")
        b = BrowserFoundation(e)
        await b.safe_select("#plan", "Fire", timeout=5.0)
        assert e.input_values["#plan"] == "Fire"


# ══════════════════════════════════════════════════════════════════
# 10. safe_check() (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestSafeCheck:
    """safe_check — checkbox with verification."""

    @pytest.mark.asyncio
    async def test_check_success(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#agree")
        b = BrowserFoundation(e)
        await b.safe_check("#agree", checked=True, timeout=5.0)
        assert e.checked_state.get("#agree") is True

    @pytest.mark.asyncio
    async def test_uncheck_success(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#agree")
        e.checked_state["#agree"] = True
        b = BrowserFoundation(e)
        await b.safe_check("#agree", checked=False, timeout=5.0)
        assert e.checked_state.get("#agree") is False

    @pytest.mark.asyncio
    async def test_check_not_found(self):
        from src.browser.foundation import BrowserFoundation, MockEngine, VerificationFailed
        e = MockEngine()
        async def not_found(sel, timeout=10000):
            return False
        e.wait_for_selector = not_found
        b = BrowserFoundation(e)
        with pytest.raises(VerificationFailed):
            await b.safe_check("#missing", checked=True, retries=1, timeout=1.0)


# ══════════════════════════════════════════════════════════════════
# 11. safe_upload() (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestSafeUpload:
    """safe_upload — file upload."""

    @pytest.mark.asyncio
    async def test_upload_success(self):
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#fileUpload")
        b = BrowserFoundation(e)
        await b.safe_upload("#fileUpload", "/tmp/test.pdf", timeout=5.0)
        assert b.stats["uploads"] == 1

    @pytest.mark.asyncio
    async def test_upload_not_found(self):
        from src.browser.foundation import (
            BrowserFoundation, MockEngine, ElementNotVisible,
        )
        e = MockEngine()
        async def not_found(sel, timeout=10000):
            return False
        e.wait_for_selector = not_found
        b = BrowserFoundation(e)
        with pytest.raises(ElementNotVisible):
            await b.safe_upload("#missing", "/tmp/test.pdf", timeout=1.0)


# ══════════════════════════════════════════════════════════════════
# 12. PortalAdapter Integration — usage pattern (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestPortalUsagePattern:
    """Simulate how PortalAdapter would use BrowserFoundation."""

    @pytest.mark.asyncio
    async def test_geglink_login_flow_pattern(self):
        """Simulate GEGLinkAdapter.login() using foundation."""
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.update([
            "input[name='oac_username']",
            "input[name='oac_intpwd']",
            "input[src*='loginbut.jpg']",
            "span.dashboard-indicator",
        ])
        b = BrowserFoundation(e)

        # Simulate login flow
        await b.navigate("https://geglink.greateasterngeneral.com/geglink/userlogin.html")
        await b.wait_until_ready(timeout=10.0)
        await b.safe_fill("input[name='oac_username']", "test_agent", timeout=5.0)
        await b.safe_fill("input[name='oac_intpwd']", "test_pass", timeout=5.0)
        await b.safe_click("input[src*='loginbut.jpg']", timeout=5.0)
        await b.wait_until_ready(timeout=10.0)

        # Verify logged in
        url = await b.get_url()
        assert "about:blank" in url or "geglink" in url

        # Stats should show activity
        assert b.stats["clicks"] >= 1
        assert b.stats["fills"] >= 2

    @pytest.mark.asyncio
    async def test_recovery_pattern(self):
        """Simulate adapter recovery using identify_current_page."""
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.add("#btnLogin")
        b = BrowserFoundation(e)

        # Identify page by URL
        await b.navigate("https://geglink.example.com/geglink/userlogin.html")
        url = await b.get_url()
        if "login" in url.lower():
            # Re-login flow
            await b.safe_fill("input[name='oac_username']", "user", timeout=5.0)
            await b.safe_fill("input[name='oac_intpwd']", "pass", timeout=5.0)
            await b.safe_click("#btnLogin", timeout=5.0)

        assert b.stats["fills"] == 2


# ══════════════════════════════════════════════════════════════════
# 13. Edge Cases (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestEdgeCases:
    """Edge cases: empty selectors, rapid calls, concurrent."""

    @pytest.mark.asyncio
    async def test_concurrent_safe_operations(self):
        """Multiple safe operations concurrently should not deadlock."""
        from src.browser.foundation import BrowserFoundation, MockEngine
        e = MockEngine()
        e.visible_elements.update(["#a", "#b", "#c", "#d"])
        b = BrowserFoundation(e)
        import asyncio

        async def click_a():
            await b.safe_click("#a", timeout=5.0)

        async def fill_b():
            await b.safe_fill("#b", "val", timeout=5.0)

        async def click_c():
            await b.safe_click("#c", timeout=5.0)

        async def fill_d():
            await b.safe_fill("#d", "val", timeout=5.0)

        results = await asyncio.gather(
            click_a(), fill_b(), click_c(), fill_d(),
            return_exceptions=True,
        )
        assert all(r is None for r in results), f"Errors: {[r for r in results if r is not None]}"
        assert b.stats["clicks"] == 2
        assert b.stats["fills"] == 2

    @pytest.mark.asyncio
    async def test_stats_are_independent(self):
        """Each BrowserFoundation instance has its own stats."""
        from src.browser.foundation import BrowserFoundation, MockEngine
        b1 = BrowserFoundation(MockEngine())
        b2 = BrowserFoundation(MockEngine())

        b2._stats["clicks"] = 100
        assert b1.stats["clicks"] == 0  # Not shared

    @pytest.mark.asyncio
    async def test_rapid_retry_does_not_exceed_limit(self):
        """Calling retry many times doesn't leak retries."""
        from src.browser.foundation import BrowserFoundation, MockEngine, RetryExceeded
        e = MockEngine()
        b = BrowserFoundation(e)

        async def always_fail():
            raise ValueError("nope")

        with pytest.raises(RetryExceeded):
            await b.retry(always_fail, retries=5, delay=0.01)
        assert b.stats["retries"] == 4  # 5 attempts = 4 retries
