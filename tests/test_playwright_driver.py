"""Tests: Playwright Driver (Phase 5).

Tests the PlaywrightSession implementation of BrowserSession.
These tests DO launch a real headless browser (Playwright).

Run with:
    pytest tests/test_playwright_driver.py -v

Skip if Playwright not installed:
    pytest tests/test_playwright_driver.py -v --skip-pw
"""

from __future__ import annotations

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Skip all tests if Playwright not installed
pytestmark = pytest.mark.skipif(
    os.environ.get("INSURE_DESK_TEST_PW") != "1",
    reason="Playwright tests disabled (set INSURE_DESK_TEST_PW=1)",
)

pytest_plugins = ("pytest_asyncio",)


# ══════════════════════════════════════════════════════════════════
# 1. PlaywrightSession Lifecycle (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestPlaywrightLifecycle:
    """PlaywrightSession start/close lifecycle."""

    @pytest.mark.asyncio
    async def test_import_playwright_session(self):
        """PlaywrightSession can be imported."""
        from src.drivers.playwright import PlaywrightSession
        assert PlaywrightSession is not None

    @pytest.mark.asyncio
    async def test_start_and_close(self):
        """Start and close a headless browser."""
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        assert session._started is True
        await session.close()
        assert session._closed is True

    @pytest.mark.asyncio
    async def test_new_page(self):
        """Open a new page after starting."""
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        assert page is not None
        assert await page.url() == "about:blank"
        await session.close()

    @pytest.mark.asyncio
    async def test_new_page_before_start_raises(self):
        """new_page before start raises BrowserClosed."""
        from src.drivers.playwright import PlaywrightSession
        from src.runtime.browser_session import BrowserClosed
        session = PlaywrightSession(headless=True)
        with pytest.raises(BrowserClosed):
            await session.new_page()

    @pytest.mark.asyncio
    async def test_double_close_safe(self):
        """Calling close() twice is safe."""
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        await session.close()
        await session.close()  # Should not raise
        assert session._closed is True


# ══════════════════════════════════════════════════════════════════
# 2. PlaywrightPage Basic Operations (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestPlaywrightPage:
    """PlaywrightPage navigation and element interactions."""

    @pytest.mark.asyncio
    async def test_goto_page(self):
        """Navigate to a URL and verify."""
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<h1>Hello</h1>")
        url = await page.url()
        assert "data:" in url
        await session.close()

    @pytest.mark.asyncio
    async def test_page_title(self):
        """Get page title after navigation."""
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<title>Test Page</title><h1>Hello</h1>")
        title = await page.title()
        assert title == "Test Page"
        await session.close()

    @pytest.mark.asyncio
    async def test_fill_input(self):
        """Fill an input field."""
        from src.runtime.browser_session import Selector
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<input id='name' type='text'>")
        await page.fill(Selector.id("name"), "Test User")
        value = await page.evaluate("document.getElementById('name').value")
        assert value == "Test User"
        await session.close()

    @pytest.mark.asyncio
    async def test_click_element(self):
        """Click an element."""
        from src.runtime.browser_session import Selector
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<button id='btn' onclick='window.clicked=true'>Click</button>")
        await page.click(Selector.id("btn"))
        clicked = await page.evaluate("window.clicked")
        assert clicked is True
        await session.close()

    @pytest.mark.asyncio
    async def test_text_content(self):
        """Get visible text from an element."""
        from src.runtime.browser_session import Selector
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<p id='msg'>Hello World</p>")
        text = await page.text(Selector.id("msg"))
        assert text == "Hello World"
        await session.close()


# ══════════════════════════════════════════════════════════════════
# 3. BrowserFactory Integration (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestBrowserFactory:
    """BrowserFactory registration and creation."""

    def test_factory_has_playwright(self):
        """Playwright is registered in BrowserFactory."""
        from src.runtime.browser_session import BrowserFactory
        available = BrowserFactory.available()
        names = [n for n, _ in available]
        assert "playwright" in names

    def test_factory_capabilities(self):
        """Factory returns capabilities for registered drivers."""
        from src.runtime.browser_session import BrowserFactory
        caps = BrowserFactory.capabilities("playwright")
        assert caps is not None
        assert caps.screenshots is True
        assert caps.javascript is True
        assert caps.multiple_tabs is True

    def test_factory_unknown_driver_raises(self):
        """Factory raises ValueError for unknown drivers."""
        from src.runtime.browser_session import BrowserFactory
        import pytest
        with pytest.raises(ValueError, match="Unknown"):
            BrowserFactory.create("nonexistent_driver")

    @pytest.mark.asyncio
    async def test_factory_create_playwright(self):
        """Create PlaywrightSession via factory."""
        from src.runtime.browser_session import BrowserFactory
        from src.drivers.playwright import PlaywrightSession
        session = BrowserFactory.create("playwright", headless=True)
        assert isinstance(session, PlaywrightSession) is True


# ══════════════════════════════════════════════════════════════════
# 4. Error Translation (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestPlaywrightErrorTranslation:
    """Playwright errors are translated to BrowserError types."""

    @pytest.mark.asyncio
    async def test_wait_for_timeout(self):
        """Wait for non-existent element raises BrowserTimeout."""
        from src.runtime.browser_session import Selector, BrowserTimeout
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<h1>Hi</h1>")
        with pytest.raises(BrowserTimeout):
            await page.wait_for(Selector.id("nonexistent"), timeout=1.0)
        await session.close()

    @pytest.mark.asyncio
    async def test_click_nonexistent_element(self):
        """Click on missing element raises BrowserTimeout or ElementNotFound."""
        from src.runtime.browser_session import Selector, BrowserTimeout
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<h1>Hi</h1>")
        with pytest.raises(BrowserTimeout):
            await page.click(Selector.id("no-such-button"), timeout=1.0)
        await session.close()

    @pytest.mark.asyncio
    async def test_screenshot(self):
        """Take a screenshot returns bytes."""
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<h1>Screenshot Test</h1>")
        data = await page.screenshot()
        assert isinstance(data, bytes)
        assert len(data) > 100  # Should be a real PNG
        await session.close()

    @pytest.mark.asyncio
    async def test_evaluate_javascript(self):
        """Execute JavaScript returns result."""
        from src.drivers.playwright import PlaywrightSession
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("data:text/html,<script>window.answer = 42</script>")
        result = await page.evaluate("window.answer")
        assert result == 42
        await session.close()
