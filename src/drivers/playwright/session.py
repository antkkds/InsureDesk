"""InsureDesk Drivers — Playwright Session Implementation.

Wraps Playwright browser in the BrowserSession abstract interface.
Registers with BrowserFactory on import.

Key design:
- Only chromium is installed/used (configurable)
- All errors translated to BrowserError types
- SessionContext tracks execution state
"""

from __future__ import annotations

from typing import Optional

from src.runtime.browser_session import (
    BrowserSession,
    BrowserPage,
    Credentials,
    SessionContext,
    DriverCapabilities,
    BrowserFactory,
    BrowserTimeout,
    ElementNotFound,
    NavigationFailed,
    AuthenticationFailed,
    SessionExpired,
    BrowserClosed,
)
from src.drivers.playwright.page import PlaywrightPage


class PlaywrightSession(BrowserSession):
    """Playwright-based browser session.

    Usage:
        session = PlaywrightSession(headless=True)
        await session.start()
        page = await session.new_page()
        await page.goto("https://example.com")
        data = await page.text(Selector.css("h1"))
        await session.close()
    """

    def __init__(self, headless: bool = True, browser_type: str = "chromium"):
        super().__init__()
        self._headless = headless
        self._browser_type = browser_type
        self._playwright = None
        self._browser = None
        self._context = None
        self._started = False
        self._closed = False

    @property
    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            screenshots=True,
            javascript=True,
            multiple_tabs=True,
            download_support=True,
            headless=self._headless,
            attach_existing=False,
            name="playwright",
        )

    async def start(self) -> None:
        """Launch Playwright browser."""
        if self._started:
            return

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()

        browser_launcher = {
            "chromium": self._playwright.chromium,
            "firefox": self._playwright.firefox,
            "webkit": self._playwright.webkit,
        }.get(self._browser_type)

        if not browser_launcher:
            raise ValueError(f"Unsupported browser type: {self._browser_type}")

        self._browser = await browser_launcher.launch(headless=self._headless)
        self._context = await self._browser.new_context()
        self._started = True
        self._context_obj.started_at = __import__("datetime").datetime.utcnow()

    @property
    def _context_obj(self) -> SessionContext:
        return self._context

    async def login(self, credentials: Credentials) -> bool:
        """Log in via Playwright.

        Navigates to login URL, fills credentials, clicks login button.
        """
        if not self._started:
            raise BrowserClosed("Session not started")
        if not credentials.username or not credentials.password:
            raise AuthenticationFailed("Missing username or password")

        try:
            page = await self.new_page()

            if credentials.url:
                await page.goto(credentials.url)

            # Try to find and fill login form
            from src.runtime.browser_session import Selector

            # Try common login field selectors
            username_fields = [
                Selector.id("username"),
                Selector.id("email"),
                Selector.css('input[type="email"]'),
                Selector.css('input[name="username"]'),
                Selector.css('input[name="email"]'),
            ]
            for sel in username_fields:
                if await page.exists(sel):
                    await page.fill(sel, credentials.username)
                    break

            password_fields = [
                Selector.id("password"),
                Selector.css('input[type="password"]'),
                Selector.css('input[name="password"]'),
            ]
            for sel in password_fields:
                if await page.exists(sel):
                    await page.fill(sel, credentials.password)
                    break

            # Try to click login/submit button
            login_buttons = [
                Selector.testid("login-button"),
                Selector.css('button[type="submit"]'),
                Selector.css('input[type="submit"]'),
                Selector.text("Sign In"),
                Selector.text("Log In"),
                Selector.text("Login"),
            ]
            for sel in login_buttons:
                if await page.exists(sel):
                    await page.click(sel)
                    break

            # Update context
            self._context_obj.logged_in = True
            self._context_obj.authenticated_user = credentials.username
            self._context_obj.current_url = await page.url()

            return True

        except BrowserClosed:
            raise
        except Exception as e:
            raise AuthenticationFailed(str(e))

    async def new_page(self) -> BrowserPage:
        """Open a new browser tab."""
        if not self._started or self._browser is None:
            raise BrowserClosed("Session not started. Call start() first.")
        if self._closed:
            raise BrowserClosed("Session is closed")

        pw_page = await self._context.new_page()
        return PlaywrightPage(pw_page)

    async def close(self) -> None:
        """Close browser and release resources."""
        if self._closed:
            return
        self._closed = True
        self._started = False

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


# ── Register with BrowserFactory ──

BrowserFactory.register(
    "playwright",
    PlaywrightSession,
    capabilities=DriverCapabilities(
        screenshots=True,
        javascript=True,
        multiple_tabs=True,
        download_support=True,
        headless=True,
        attach_existing=False,
        name="playwright",
        version="1.0.0",
    ),
)
