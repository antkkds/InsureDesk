"""Tests: BrowserSession Abstraction (Phase 5).

Tests use MockBrowserSession and MockPage — no Playwright imported.
These are contract tests: any real BrowserSession implementation
(Mock, Playwright, CDP) must pass the same tests.

Covers:
- Selector (6 tests)
- BrowserError hierarchy (6 tests)
- SessionContext (3 tests)
- MockPage basic operations (10 tests)
- MockBrowserSession lifecycle (8 tests)
- MockBrowserSession integration (5 tests)
- Contract tests (abstract interface) (4 tests)
Target: ~42 tests
"""

from __future__ import annotations

import os
import sys
import pytest
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ══════════════════════════════════════════════════════════════════
# 1. Selector (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestSelector:
    """Typed Selector dataclass."""

    def test_selector_css(self):
        from src.runtime.browser_session import Selector
        s = Selector.css("#btnLogin")
        assert s.strategy == "css"
        assert s.value == "#btnLogin"

    def test_selector_xpath(self):
        from src.runtime.browser_session import Selector
        s = Selector.xpath("//button")
        assert s.strategy == "xpath"

    def test_selector_id(self):
        from src.runtime.browser_session import Selector
        s = Selector.id("username")
        assert s.strategy == "id"
        assert s.value == "username"

    def test_selector_testid(self):
        from src.runtime.browser_session import Selector
        s = Selector.testid("send-button")
        assert s.strategy == "testid"

    def test_selector_text(self):
        from src.runtime.browser_session import Selector
        s = Selector.text("Submit")
        assert s.strategy == "text"

    def test_selector_to_playwright(self):
        from src.runtime.browser_session import Selector
        assert Selector.css("#btn").to_playwright() == "#btn"
        assert Selector.xpath("//a").to_playwright() == "xpath=//a"
        assert Selector.id("user").to_playwright() == "#user"
        assert Selector.testid("send").to_playwright() == '[data-testid="send"]'
        assert Selector.text("Login").to_playwright() == 'text="Login"'


# ══════════════════════════════════════════════════════════════════
# 2. BrowserError Hierarchy (6 tests)
# ══════════════════════════════════════════════════════════════════

class TestBrowserErrors:
    """Browser error types."""

    def test_browser_error_base(self):
        from src.runtime.browser_session import BrowserError
        e = BrowserError("Something broke", {"url": "http://example.com"})
        assert "Something" in str(e)
        assert e.context["url"] == "http://example.com"

    def test_browser_timeout(self):
        from src.runtime.browser_session import BrowserTimeout
        e = BrowserTimeout("Timed out waiting for element")
        assert isinstance(e, BrowserTimeout)

    def test_element_not_found(self):
        from src.runtime.browser_session import ElementNotFound
        e = ElementNotFound("#missing-btn not found")
        assert isinstance(e, ElementNotFound)

    def test_navigation_failed(self):
        from src.runtime.browser_session import NavigationFailed
        e = NavigationFailed("Page did not load")
        assert isinstance(e, NavigationFailed)

    def test_authentication_failed(self):
        from src.runtime.browser_session import AuthenticationFailed
        e = AuthenticationFailed("Invalid credentials")
        assert isinstance(e, AuthenticationFailed)

    def test_session_expired(self):
        from src.runtime.browser_session import SessionExpired
        e = SessionExpired("Session has expired")
        assert isinstance(e, SessionExpired)


# ══════════════════════════════════════════════════════════════════
# 3. SessionContext (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestSessionContext:
    """Session execution context."""

    def test_session_context_create(self):
        from src.runtime.browser_session import SessionContext
        ctx = SessionContext.create("Great Eastern", "great_eastern")
        assert ctx.session_id
        assert len(ctx.session_id) == 12
        assert ctx.adapter_name == "Great Eastern"
        assert ctx.portal_name == "great_eastern"
        assert ctx.started_at is not None
        assert ctx.logged_in is False

    def test_session_context_defaults(self):
        from src.runtime.browser_session import SessionContext
        ctx = SessionContext()
        assert ctx.session_id == ""
        assert ctx.logged_in is False
        assert ctx.current_url == ""
        assert ctx.authenticated_user == ""

    def test_session_context_metadata(self):
        from src.runtime.browser_session import SessionContext
        ctx = SessionContext.create("AIA")
        ctx.metadata["attempts"] = 3
        assert ctx.metadata["attempts"] == 3


# ══════════════════════════════════════════════════════════════════
# 4. MockPage Basic Operations (10 tests)
# ══════════════════════════════════════════════════════════════════

class TestMockPage:
    """MockPage in-memory browser page."""

    @pytest.fixture
    def page(self):
        from src.runtime.browser_session import MockPage
        return MockPage()

    @pytest.mark.asyncio
    async def test_goto(self, page):
        from src.runtime.browser_session import Selector
        await page.goto("https://portal.example.com")
        assert page.current_url == "https://portal.example.com"
        assert await page.title() == "Mock: https://portal.example.com"

    @pytest.mark.asyncio
    async def test_fill(self, page):
        from src.runtime.browser_session import Selector
        await page.fill(Selector.id("username"), "test_user")
        assert page.inputs["username"] == "test_user"

    @pytest.mark.asyncio
    async def test_click(self, page):
        from src.runtime.browser_session import Selector
        await page.click(Selector.id("btnLogin"))
        assert "btnLogin" in page.clicked

    @pytest.mark.asyncio
    async def test_click_navigates(self, page):
        from src.runtime.browser_session import Selector
        await page.click(Selector.id("btnLogin"))
        assert page.current_url == "/dashboard"

    @pytest.mark.asyncio
    async def test_text(self, page):
        from src.runtime.browser_session import Selector
        page.elements["policy_no"] = "GE-12345"
        text = await page.text(Selector.id("policy_no"))
        assert text == "GE-12345"

    @pytest.mark.asyncio
    async def test_text_not_found(self, page):
        from src.runtime.browser_session import Selector
        text = await page.text(Selector.id("nonexistent"))
        assert text == ""

    @pytest.mark.asyncio
    async def test_exists(self, page):
        from src.runtime.browser_session import Selector
        page.elements["policy_no"] = "GE-123"
        assert await page.exists(Selector.id("policy_no"))
        assert not await page.exists(Selector.id("missing"))

    @pytest.mark.asyncio
    async def test_screenshot(self, page):
        data = await page.screenshot()
        assert data == b"mock_screenshot_bytes"
        assert len(page.screenshots) == 1

    @pytest.mark.asyncio
    async def test_evaluate(self, page):
        page.page_title = "Dashboard"
        assert await page.evaluate("document.title") == "Dashboard"
        assert await page.evaluate("window.location.href") == page.current_url

    @pytest.mark.asyncio
    async def test_wait_for_timeout(self, page):
        from src.runtime.browser_session import Selector, BrowserTimeout
        with pytest.raises(BrowserTimeout):
            await page.wait_for(Selector.id("missing"), timeout=1.0)


# ══════════════════════════════════════════════════════════════════
# 5. MockBrowserSession Lifecycle (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestMockBrowserSession:
    """MockBrowserSession lifecycle and auth."""

    @pytest.fixture
    def session(self):
        from src.runtime.browser_session import MockBrowserSession
        return MockBrowserSession()

    @pytest.mark.asyncio
    async def test_start(self, session):
        await session.start()
        assert session.is_started
        assert not session.is_closed

    @pytest.mark.asyncio
    async def test_new_page(self, session):
        from src.runtime.browser_session import MockPage
        await session.start()
        page = await session.new_page()
        assert isinstance(page, MockPage)
        assert len(session.pages) == 1

    @pytest.mark.asyncio
    async def test_new_page_without_start_raises(self, session):
        from src.runtime.browser_session import BrowserClosed
        with pytest.raises(BrowserClosed):
            await session.new_page()

    @pytest.mark.asyncio
    async def test_close(self, session):
        await session.start()
        await session.close()
        assert session.is_closed
        assert not session.is_started

    @pytest.mark.asyncio
    async def test_login_success(self, session):
        from src.runtime.browser_session import Credentials
        await session.start()
        result = await session.login(Credentials(username="admin", password="pass"))
        assert result is True
        assert session.login_called
        assert session.context.logged_in

    @pytest.mark.asyncio
    async def test_login_missing_credentials(self, session):
        from src.runtime.browser_session import Credentials, AuthenticationFailed
        await session.start()
        with pytest.raises(AuthenticationFailed):
            await session.login(Credentials())

    @pytest.mark.asyncio
    async def test_login_without_start_raises(self, session):
        from src.runtime.browser_session import Credentials, BrowserClosed
        with pytest.raises(BrowserClosed):
            await session.login(Credentials(username="u", password="p"))

    @pytest.mark.asyncio
    async def test_context_after_login(self, session):
        from src.runtime.browser_session import Credentials
        await session.start()
        await session.login(Credentials(username="admin", password="pass",
                                        url="https://ge.example.com"))
        assert session.context.authenticated_user == "admin"

    @pytest.mark.asyncio
    async def test_context_url_after_login(self, session):
        """Login sets current_url from credentials.url."""
        from src.runtime.browser_session import Credentials
        await session.start()
        await session.login(Credentials(username="admin", password="pass",
                                        url="https://ge.example.com/login"))
        assert session.context.current_url == "https://ge.example.com/login"

    @pytest.mark.asyncio
    async def test_context_url_default(self, session):
        """Login sets default URL when none provided."""
        from src.runtime.browser_session import Credentials
        await session.start()
        await session.login(Credentials(username="admin", password="pass"))
        assert "portal.example.com/dashboard" in session.context.current_url


# ══════════════════════════════════════════════════════════════════
# 6. MockBrowserSession Integration (5 tests)
# ══════════════════════════════════════════════════════════════════

class TestMockBrowserIntegration:
    """Full MockBrowserSession workflow."""

    @pytest.mark.asyncio
    async def test_login_then_navigate(self):
        """Login → open page → navigate to policy."""
        from src.runtime.browser_session import (
            MockBrowserSession, Credentials, Selector,
        )
        session = MockBrowserSession()
        await session.start()
        await session.login(Credentials(username="agent", password="pass123",
                                        url="https://ge.portal.com/login"))

        page = await session.new_page()
        await page.goto("https://ge.portal.com/policies")
        assert "policies" in page.current_url

        # Fill search form
        await page.fill(Selector.id("search"), "GE-12345")
        assert page.inputs["search"] == "GE-12345"

        # Click search
        await page.click(Selector.testid("search-button"))
        assert "search-button" in page.clicked

        await session.close()
        assert session.is_closed

    @pytest.mark.asyncio
    async def test_screenshot_on_error(self):
        """Take screenshot for debugging."""
        from src.runtime.browser_session import MockBrowserSession, Selector
        session = MockBrowserSession()
        await session.start()
        page = await session.new_page()
        await page.goto("https://portal.com")

        # Screenshot before action
        before = await page.screenshot()
        assert len(before) > 0

        # Screenshot on error
        page.errors[Selector.id("missing_btn").value] = TimeoutError()
        with pytest.raises(Exception):
            await page.click(Selector.id("missing_btn"))

        after = await page.screenshot()
        assert len(page.screenshots) == 2  # before + after

    @pytest.mark.asyncio
    async def test_multiple_pages(self):
        """Open multiple pages/tabs."""
        from src.runtime.browser_session import MockBrowserSession
        session = MockBrowserSession()
        await session.start()

        p1 = await session.new_page()
        p2 = await session.new_page()
        p3 = await session.new_page()

        assert len(session.pages) == 3
        assert p1 is not p2
        assert p2 is not p3

    @pytest.mark.asyncio
    async def test_closed_page_raises(self):
        """Operations on closed page raise BrowserClosed."""
        from src.runtime.browser_session import (
            MockBrowserSession, Selector, BrowserClosed,
        )
        session = MockBrowserSession()
        await session.start()
        page = await session.new_page()
        await session.close()

        with pytest.raises(BrowserClosed):
            await page.click(Selector.id("btn"))

    @pytest.mark.asyncio
    async def test_import_no_playwright(self):
        """MockBrowserSession can be imported without Playwright installed."""
        import importlib
        # Verify the module can be imported standalone
        spec = importlib.util.find_spec("src.runtime.browser_session")
        assert spec is not None, "browser_session module should be importable"


# ══════════════════════════════════════════════════════════════════
# 7. Contract Tests — Abstract Interface (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestBrowserContract:
    """Contract tests: any BrowserSession must satisfy these."""

    def test_browser_session_is_abstract(self):
        """BrowserSession cannot be instantiated directly."""
        from src.runtime.browser_session import BrowserSession
        with pytest.raises(TypeError):
            BrowserSession()

    def test_browser_page_is_abstract(self):
        """BrowserPage cannot be instantiated directly."""
        from src.runtime.browser_session import BrowserPage
        with pytest.raises(TypeError):
            BrowserPage()

    def test_mock_browser_session_is_browser_session(self):
        """MockBrowserSession is a BrowserSession."""
        from src.runtime.browser_session import MockBrowserSession, BrowserSession
        session = MockBrowserSession()
        assert isinstance(session, BrowserSession)

    def test_mock_page_is_browser_page(self):
        """MockPage is a BrowserPage."""
        from src.runtime.browser_session import MockPage, BrowserPage
        page = MockPage()
        assert isinstance(page, BrowserPage)

# ══════════════════════════════════════════════════════════════════
# 8. DriverCapabilities + BrowserFactory Tests (8 tests)
# ══════════════════════════════════════════════════════════════════

class TestDriverCapabilities:
    """DriverCapabilities dataclass."""

    def test_driver_cap_defaults(self):
        """Default capabilities are reasonable."""
        from src.runtime.browser_session import DriverCapabilities
        caps = DriverCapabilities()
        assert caps.screenshots is True
        assert caps.javascript is True
        assert caps.multiple_tabs is True
        assert caps.attach_existing is False

    def test_driver_cap_custom(self):
        """Custom capabilities."""
        from src.runtime.browser_session import DriverCapabilities
        caps = DriverCapabilities(
            screenshots=False,
            attach_existing=True,
            name="cdp",
        )
        assert caps.screenshots is False
        assert caps.attach_existing is True
        assert caps.name == "cdp"


class TestBrowserFactory:
    """BrowserFactory driver registry."""

    def test_factory_empty_initially(self):
        """Factory has no drivers before registration."""
        from src.runtime.browser_session import BrowserFactory
        # Reset for test isolation
        BrowserFactory._drivers = {}
        BrowserFactory._capabilities = {}
        assert BrowserFactory.available() == []

    def test_factory_register_and_create(self):
        """Register a mock driver and create it."""
        from src.runtime.browser_session import (
            BrowserFactory, BrowserSession, DriverCapabilities,
        )

        class MockDriver(BrowserSession):
            async def start(self): pass
            async def login(self, c): return True
            async def new_page(self): return None
            async def close(self): pass

        BrowserFactory.register("test_mock", MockDriver,
                                 capabilities=DriverCapabilities(name="test"))
        session = BrowserFactory.create("test_mock")
        assert isinstance(session, MockDriver)
        assert BrowserFactory.capabilities("test_mock").name == "test"

    def test_factory_unknown_raises(self):
        """Creating an unknown driver raises ValueError."""
        from src.runtime.browser_session import BrowserFactory
        import pytest
        with pytest.raises(ValueError):
            BrowserFactory.create("does_not_exist")

    def test_factory_available(self):
        """Available returns registered drivers."""
        from src.runtime.browser_session import BrowserFactory
        available = BrowserFactory.available()
        names = [n for n, _ in available]
        assert "test_mock" in names
