"""InsureDesk — Playwright Driver (Development).

Full browser automation via Playwright.
Used for development, testing, CI, and selector debugging.
NOT shipped to customers — replaced by QtDriver in production.
"""

from typing import Optional, List, Any
import asyncio

from src.browser.driver import BrowserEngine, PageInfo, Cookie, cookie_to_dict, dict_to_cookie


def _playwright_available() -> bool:
    """Check if Playwright is importable."""
    try:
        import playwright
        return True
    except ImportError:
        return False


class PlaywrightDriver(BrowserEngine):
    """Browser driver using Playwright (dev/testing only).

    Opens a real browser window (Chromium).
    Requires: pip install playwright && python -m playwright install chromium
    """

    def __init__(self):
        self._browser = None
        self._context = None
        self._page = None
        self._playwright = None
        self._running = False

    @property
    def name(self) -> str:
        return "playwright"

    async def start(self, headless: bool = False, port: int = 0) -> bool:
        """Start Playwright and launch Chromium."""
        if self._running:
            return True

        if not _playwright_available():
            raise RuntimeError(
                "Playwright not installed. Run:\n"
                "  pip install playwright\n"
                "  python -m playwright install chromium"
            )

        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=headless,
            args=["--start-maximized"] if not headless else [],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self._running = True
        return True

    async def stop(self):
        """Stop Playwright and close browser."""
        self._running = False
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
        self._context = None
        self._page = None

    async def navigate(self, url: str, timeout: int = 30000) -> bool:
        """Navigate to a URL."""
        if not self._page:
            return False
        try:
            await self._page.goto(url, timeout=timeout, wait_until="networkidle")
            return True
        except Exception:
            try:
                await self._page.goto(url, timeout=timeout, wait_until="load")
                return True
            except Exception:
                return False

    async def get_url(self) -> str:
        return self._page.url if self._page else ""

    async def get_title(self) -> str:
        return await self._page.title() if self._page else ""

    async def get_page_info(self) -> PageInfo:
        if not self._page:
            return PageInfo()
        try:
            return PageInfo(
                url=self._page.url,
                title=await self._page.title(),
                html=await self._page.content(),
                text=await self._page.evaluate("document.body.innerText"),
            )
        except Exception:
            return PageInfo(url=self._page.url)

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        if not self._page:
            return False
        try:
            await self._page.click(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        if not self._page:
            return False
        try:
            await self._page.click(selector)
            await self._page.fill(selector, "")
            await self._page.type(selector, value, delay=delay_ms)
            return True
        except Exception:
            return False

    async def select_option(self, selector: str, value: str) -> bool:
        if not self._page:
            return False
        try:
            await self._page.select_option(selector, value)
            return True
        except Exception:
            return False

    async def is_checked(self, selector: str) -> bool:
        if not self._page:
            return False
        try:
            return await self._page.is_checked(selector)
        except Exception:
            return False

    async def set_checked(self, selector: str, checked: bool) -> bool:
        if not self._page:
            return False
        try:
            is_checked = await self._page.is_checked(selector)
            if checked != is_checked:
                await self._page.click(selector)
            return True
        except Exception:
            return False

    async def upload_file(self, selector: str, file_path: str) -> bool:
        if not self._page:
            return False
        try:
            await self._page.set_input_files(selector, file_path)
            return True
        except Exception:
            return False

    async def get_text(self, selector: str) -> str:
        if not self._page:
            return ""
        try:
            el = await self._page.query_selector(selector)
            return await el.inner_text() if el else ""
        except Exception:
            return ""

    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        if not self._page:
            return None
        try:
            return await self._page.get_attribute(selector, attr)
        except Exception:
            return None

    async def is_visible(self, selector: str) -> bool:
        if not self._page:
            return False
        try:
            return await self._page.is_visible(selector)
        except Exception:
            return False

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        if not self._page:
            return False
        try:
            await self._page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def wait_for_navigation(self, timeout: int = 30000) -> bool:
        if not self._page:
            return False
        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
            return True
        except Exception:
            return False

    async def evaluate(self, script: str) -> Any:
        if not self._page:
            return None
        try:
            return await self._page.evaluate(script)
        except Exception:
            return None

    async def screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        if not self._page:
            return None
        try:
            return await self._page.screenshot(path=path) if not path else await self._page.screenshot(path=path)
        except Exception:
            return None

    async def get_cookies(self) -> List[Cookie]:
        if not self._context:
            return []
        try:
            raw = await self._context.cookies()
            return [Cookie(
                name=c.get("name", ""),
                value=c.get("value", ""),
                domain=c.get("domain", ""),
                path=c.get("path", "/"),
                secure=c.get("secure", False),
                http_only=c.get("httpOnly", False),
                same_site=c.get("sameSite", "Lax"),
                expires=c.get("expires", 0),
            ) for c in raw]
        except Exception:
            return []

    async def set_cookies(self, cookies: List[Cookie]):
        if not self._context:
            return
        try:
            raw = [cookie_to_dict(c) for c in cookies]
            await self._context.add_cookies(raw)
        except Exception:
            pass

    async def clear_cookies(self):
        if self._context:
            try:
                await self._context.clear_cookies()
            except Exception:
                pass

    async def get_tabs(self) -> int:
        if not self._context:
            return 0
        return len(self._context.pages)

    async def switch_tab(self, index: int) -> bool:
        if not self._context:
            return False
        pages = self._context.pages
        if 0 <= index < len(pages):
            self._page = pages[index]
            await self._page.bring_to_front()
            return True
        return False

    async def close_tab(self, index: int = -1):
        if not self._context:
            return
        pages = self._context.pages
        if index < 0:
            index = len(pages) - 1
        if 0 <= index < len(pages):
            await pages[index].close()
            if self._page == pages[index] and len(pages) > 1:
                self._page = pages[0]
