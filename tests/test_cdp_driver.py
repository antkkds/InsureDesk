"""Tests: CDP Driver (Phase 5).

Tests the CdpSession implementation of BrowserSession.
These tests connect to the existing Chrome instance on port 9222.

Skip if Chrome CDP not available:
    pytest tests/test_cdp_driver.py -v --skip-cdp
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Skip if CDP not available
skip_if_no_cdp = pytest.mark.skipif(
    os.environ.get("INSURE_DESK_TEST_CDP") != "1",
    reason="CDP tests disabled (set INSURE_DESK_TEST_CDP=1)",
)


# ══════════════════════════════════════════════════════════════════
# 1. CdpSession Lifecycle (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCdpLifecycle:
    """CdpSession start/close lifecycle."""

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_import_cdp_session(self):
        """CdpSession can be imported."""
        from src.drivers.cdp import CdpSession
        assert CdpSession is not None

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_start(self):
        """Connect to existing Chrome via CDP."""
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        assert session._started is True
        await session.close()

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_new_page(self):
        """Open a new tab."""
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        assert page is not None
        url = await page.url()
        assert "about:blank" in url or url == "about:blank"
        await session.close()

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_new_page_before_start_raises(self):
        """new_page before start raises BrowserClosed."""
        from src.drivers.cdp import CdpSession
        from src.runtime.browser_session import BrowserClosed
        session = CdpSession(port=9222)
        with pytest.raises(BrowserClosed):
            await session.new_page()

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_double_close_safe(self):
        """Calling close() twice is safe."""
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        await session.close()
        await session.close()
        assert session._closed is True


# ══════════════════════════════════════════════════════════════════
# 2. CdpPage Basic Operations (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestCdpPage:
    """CdpPage navigation and element interactions."""

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_navigate_and_title(self):
        """Navigate to a page and get title."""
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<title>CDP Test</title><h1>Hello</h1>")
        title = await page.title()
        assert title == "CDP Test"
        await session.close()

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_fill_input(self):
        """Fill an input field via CDP JavaScript injection."""
        from src.runtime.browser_session import Selector
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<input id='name' type='text'>")
        await page.fill(Selector.id("name"), "Test User")
        value = await page.evaluate("document.getElementById('name').value")
        assert value == "Test User"
        await session.close()

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_click_element(self):
        """Click an element via CDP."""
        from src.runtime.browser_session import Selector
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        await page.goto(
            "data:text/html,"
            "<button id='btn' onclick='window.clicked=true'>Click</button>"
        )
        await page.click(Selector.id("btn"))
        clicked = await page.evaluate("window.clicked")
        assert clicked is True
        await session.close()

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_text_content(self):
        """Get visible text from an element."""
        from src.runtime.browser_session import Selector
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<p id='msg'>Hello World</p>")
        text = await page.text(Selector.id("msg"))
        assert text == "Hello World"
        await session.close()

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_screenshot(self):
        """Take a screenshot returns PNG bytes."""
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<h1>CDP Screenshot</h1>")
        data = await page.screenshot()
        assert isinstance(data, bytes)
        assert len(data) > 100
        await session.close()


# ══════════════════════════════════════════════════════════════════
# 3. BrowserFactory + CDP (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestCdpFactory:
    """BrowserFactory integration with CDP driver."""

    @skip_if_no_cdp
    def test_factory_has_cdp(self):
        """CDP is registered in BrowserFactory."""
        from src.runtime.browser_session import BrowserFactory
        available = BrowserFactory.available()
        names = [n for n, _ in available]
        assert "cdp" in names

    @skip_if_no_cdp
    def test_factory_capabilities_cdp(self):
        """CDP capabilities include attach_existing=True."""
        from src.runtime.browser_session import BrowserFactory
        caps = BrowserFactory.capabilities("cdp")
        assert caps is not None
        assert caps.attach_existing is True
        assert caps.name == "cdp"

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_factory_create_cdp(self):
        """Create CdpSession via factory."""
        from src.runtime.browser_session import BrowserFactory
        session = BrowserFactory.create("cdp", port=9222)
        from src.drivers.cdp import CdpSession
        assert isinstance(session, CdpSession) is True


# ══════════════════════════════════════════════════════════════════
# 4. Error Handling (2 tests)
# ══════════════════════════════════════════════════════════════════

class TestCdpErrors:
    """CDP error translation."""

    @skip_if_no_cdp
    @pytest.mark.asyncio
    async def test_click_nonexistent(self):
        """Click on missing element raises ElementNotFound."""
        from src.runtime.browser_session import Selector, ElementNotFound, BrowserTimeout
        from src.drivers.cdp import CdpSession
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<h1>Hi</h1>")
        # CDP uses JS injection — non-existent element returns false
        # which raises ElementNotFound from click()
        with pytest.raises((ElementNotFound, BrowserTimeout)):
            await page.click(Selector.id("no-such-button"))
        await session.close()
