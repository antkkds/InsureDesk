"""InsureDesk — Form Engine.

Shared form interaction layer for portal automation.
Every PortalAdapter uses FormEngine instead of calling browser directly.

Works with ANY BrowserDriver implementation (PlaywrightDriver, QtDriver).
"""

from typing import Optional, List
from dataclasses import dataclass
import asyncio
import random

from src.browser.driver import BrowserEngine


@dataclass
class FormField:
    """A form field to interact with."""
    selector: str = ""
    value: str = ""
    field_type: str = "text"     # text / select / checkbox / file / radio / date
    wait_after: int = 300        # ms to wait after interaction
    iframe: str = ""             # optional iframe selector


class FormEngine:
    """Shared form interaction layer.

    All portal adapters use this — never call browser actions directly.
    Supports both Playwright (dev) and QtWebEngine (production) backends.
    """

    def __init__(self, engine: Optional[BrowserEngine] = None):
        self.engine = engine
        self._page = None  # legacy Playwright support

    @property
    def browser(self):
        """Keep backward compat with PortalAdapter."""
        return self.engine

    @browser.setter
    def browser(self, engine):
        self.engine = engine

    async def fill_text(self, selector: str, value: str, iframe: str = ""):
        """Type text into a field with human-like delays."""
        if self.engine:
            await self.engine.fill(selector, value)
        elif self._page:
            await self._legacy_fill(selector, value, iframe)
        await self._delay(100, 300)

    async def select_option(self, selector: str, value: str, iframe: str = ""):
        """Select an option from a dropdown."""
        if self.engine:
            await self.engine.select_option(selector, value)
        elif self._page:
            page = await self._legacy_resolve_page(iframe)
            await page.select_option(selector, value)
        await self._delay(200, 500)

    async def check(self, selector: str, checked: bool = True, iframe: str = ""):
        """Check or uncheck a checkbox/radio."""
        if self.engine:
            await self.engine.set_checked(selector, checked)
        elif self._page:
            page = await self._legacy_resolve_page(iframe)
            is_checked = await page.is_checked(selector)
            if checked != is_checked:
                await page.click(selector)
        await self._delay(100, 300)

    async def upload_file(self, selector: str, file_path: str, iframe: str = ""):
        """Upload a file via file input."""
        if self.engine:
            await self.engine.upload_file(selector, file_path)
        elif self._page:
            page = await self._legacy_resolve_page(iframe)
            await page.set_input_files(selector, file_path)
        await self._delay(500, 1500)

    async def click(self, selector: str, iframe: str = ""):
        """Click an element with human-like behavior."""
        if self.engine:
            await self.engine.click(selector)
        elif self._page:
            page = await self._legacy_resolve_page(iframe)
            await page.click(selector)
        await self._delay(200, 800)

    async def navigate(self, url: str) -> Optional[object]:
        """Navigate to a URL. Returns page object (legacy) or None."""
        if self.engine:
            ok = await self.engine.navigate(url)
            return self if ok else None

        if self._page:
            await self._page.goto(url)
            return self._page
        return None

    async def get_text(self, selector: str) -> str:
        """Get visible text of an element."""
        if self.engine:
            return await self.engine.get_text(selector)
        if self._page:
            el = await self._page.query_selector(selector)
            return await el.inner_text() if el else ""
        return ""

    async def wait_for_selector(self, selector: str, timeout: int = 10000):
        """Wait for an element to appear."""
        if self.engine:
            return await self.engine.wait_for_selector(selector, timeout)
        if self._page:
            await self._page.wait_for_selector(selector, timeout=timeout)

    async def wait_for_navigation(self, timeout: int = 30000):
        """Wait for page navigation."""
        if self.engine:
            return await self.engine.wait_for_navigation(timeout)
        if self._page:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)

    async def wait_for_timeout(self, ms: int = 1000):
        """Wait for a specified duration in milliseconds."""
        await asyncio.sleep(ms / 1000)

    async def screenshot(self, path: Optional[str] = None):
        """Take a screenshot."""
        if self.engine:
            return await self.engine.screenshot(path)
        if self._page:
            return await self._page.screenshot(path=path) if path else await self._page.screenshot()
        return None

    async def evaluate(self, script: str):
        """Execute JavaScript in page context."""
        if self.engine:
            return await self.engine.evaluate(script)
        if self._page:
            return await self._page.evaluate(script)
        return None

    async def get_cookies(self) -> list:
        """Get cookies as dicts."""
        if self.engine:
            cookies = await self.engine.get_cookies()
            from src.browser.driver import cookie_to_dict
            return [cookie_to_dict(c) for c in cookies]
        if self._page:
            return await self._page.context.cookies()
        return []

    async def set_cookies(self, cookies: list):
        """Set cookies from dicts."""
        if self.engine:
            from src.browser.driver import dict_to_cookie
            engine_cookies = [dict_to_cookie(c) for c in cookies]
            await self.engine.set_cookies(engine_cookies)
        elif self._page:
            await self._page.context.add_cookies(cookies)

    # ── Legacy Playwright support ──

    def set_legacy_page(self, page):
        """Set a legacy Playwright page for backward compatibility."""
        self._page = page

    async def _legacy_resolve_page(self, iframe: str = ""):
        """Legacy: resolve iframe or return main page."""
        if iframe and self._page:
            frame = self._page.frame(iframe)
            if frame:
                return frame
        return self._page

    async def _legacy_fill(self, selector: str, value: str, iframe: str = ""):
        """Legacy: type with human-like delays."""
        page = await self._legacy_resolve_page(iframe)
        await page.click(selector)
        await self._delay(50, 150)
        await page.fill(selector, "")
        await self._delay(30, 100)
        await page.type(selector, value, delay=self._human_delay())
        await self._delay(100, 300)

    # ── Helpers ──

    @staticmethod
    def _human_delay() -> int:
        """Random human-like typing delay (30-120ms)."""
        return random.randint(30, 120)

    @staticmethod
    async def _delay(min_ms: int = 50, max_ms: int = 200):
        """Random delay to simulate human behavior."""
        await asyncio.sleep(random.randint(min_ms, max_ms) / 1000)
