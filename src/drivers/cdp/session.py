"""InsureDesk Drivers — CDP Session Implementation.

Implements BrowserSession using Chrome DevTools Protocol directly.
No Playwright needed — attaches to an existing Chrome instance.

Key features:
- attach_existing=True: connects to a running Chrome
- No Playwright dependency
- SessionContext tracks execution state
- All errors translated to BrowserError types
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
from src.drivers.cdp.page import CdpPage
from src.browser.chrome.connection import CdpConnection
from src.browser.chrome.tabs import list_tabs, create_tab


class CdpSession(BrowserSession):
    """CDP-based browser session.

    Connects to an existing Chrome instance via CDP WebSocket.
    All DOM operations use JavaScript injection for reliability.

    Usage:
        session = CdpSession(port=9222)
        await session.start()
        page = await session.new_page()
        await page.goto("https://portal.example.com")
        await session.close()
    """

    def __init__(self, port: int = 9222, host: str = "localhost"):
        super().__init__()
        self._port = port
        self._host = host
        self._browser_conn: Optional[CdpConnection] = None
        self._pages: list[CdpPage] = []
        self._started = False
        self._closed = False

    @property
    def capabilities(self) -> DriverCapabilities:
        return DriverCapabilities(
            screenshots=True,
            javascript=True,
            multiple_tabs=True,
            download_support=True,
            attach_existing=True,
            headless=False,  # CDP connects to existing GUI Chrome
            name="cdp",
            version="1.0.0",
        )

    async def start(self) -> None:
        """Connect to an existing Chrome instance via CDP."""
        if self._started:
            return

        # Discover the browser WebSocket URL
        ws_url = self._discover_browser_ws()
        if not ws_url:
            raise BrowserClosed(
                f"No Chrome instance found on {self._host}:{self._port}. "
                f"Make sure Chrome is running with --remote-debugging-port={self._port}"
            )

        # Connect to the browser WebSocket endpoint
        self._browser_conn = CdpConnection()
        await self._browser_conn.connect(ws_url)

        self._started = True
        self._context.started_at = __import__("datetime").datetime.utcnow()

    def _discover_browser_ws(self) -> Optional[str]:
        """Discover the browser WebSocket debugger URL."""
        try:
            import json, urllib.request
            req = urllib.request.Request(
                f"http://{self._host}:{self._port}/json/version"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                info = json.loads(resp.read().decode())
            return info.get("webSocketDebuggerUrl")
        except Exception:
            return None

    async def login(self, credentials: Credentials) -> bool:
        """Log in by navigating to the portal and filling credentials."""
        if not self._started:
            raise BrowserClosed("Session not started")
        if not credentials.username or not credentials.password:
            raise AuthenticationFailed("Missing username or password")

        try:
            page = await self.new_page()

            if credentials.url:
                await page.goto(credentials.url)

            # Try common login field selectors
            from src.runtime.browser_session import Selector

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

            # Try login buttons
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

            self._context.logged_in = True
            self._context.authenticated_user = credentials.username
            self._context.current_url = await page.url()

            return True

        except (BrowserClosed, AuthenticationFailed):
            raise
        except Exception as e:
            raise AuthenticationFailed(str(e))

    async def new_page(self) -> BrowserPage:
        """Open a new tab and return a CdpPage."""
        if not self._started:
            raise BrowserClosed("Session not started. Call start() first.")
        if self._closed:
            raise BrowserClosed("Session is closed")

        # Create a new tab
        tab = create_tab(self._port, "about:blank")
        if not tab:
            raise BrowserClosed("Failed to create new tab")

        # Connect to the tab via CDP
        page_conn = CdpConnection()
        await page_conn.connect(tab.ws_url)

        # Enable Page and DOM domains
        await page_conn.send_command("Page.enable")

        cdp_page = CdpPage(page_conn, tab.id, tab.url)
        self._pages.append(cdp_page)
        return cdp_page

    async def close(self) -> None:
        """Close the browser session."""
        if self._closed:
            return
        self._closed = True
        self._started = False

        self._pages.clear()

        if self._browser_conn:
            try:
                # Try to close gracefully
                await self._browser_conn.send_command("Browser.close", timeout=5.0)
            except Exception:
                pass
            self._browser_conn = None


# ── Register with BrowserFactory ──

BrowserFactory.register(
    "cdp",
    CdpSession,
    capabilities=DriverCapabilities(
        screenshots=True,
        javascript=True,
        multiple_tabs=True,
        download_support=True,
        attach_existing=True,
        headless=False,
        name="cdp",
        version="1.0.0",
    ),
)
