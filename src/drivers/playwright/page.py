"""InsureDesk Drivers — Playwright Page Implementation.

Wraps Playwright Page in the BrowserPage abstract interface.
All Playwright-specific errors are translated to BrowserError types.
"""

from __future__ import annotations

from typing import Any

from src.runtime.browser_session import (
    BrowserPage,
    Selector,
    BrowserTimeout,
    ElementNotFound,
    NavigationFailed,
    BrowserClosed,
)

# Lazy import — only when this module is used
_playwright = None


def _get_playwright():
    global _playwright
    if _playwright is None:
        try:
            from playwright.async_api import TimeoutError as PWTimeout
            from playwright.async_api import Error as PWError
            _playwright = (PWTimeout, PWError)
        except ImportError:
            raise ImportError(
                "Playwright is not installed. "
                "Run: pip install playwright && playwright install chromium"
            )
    return _playwright


def _translate_error(pw_error: Exception, context: str = "") -> Exception:
    """Translate Playwright-specific errors to BrowserError types."""
    PWTimeout, PWError = _get_playwright()

    msg = str(pw_error) or f"Playwright error during {context}" if context else str(pw_error)

    if isinstance(pw_error, PWTimeout):
        return BrowserTimeout(msg)
    if isinstance(pw_error, PWError):
        msg_lower = msg.lower()
        if "doesn't exist" in msg_lower or "did not find" in msg_lower or "no node" in msg_lower:
            return ElementNotFound(msg)
        if "navigate" in msg_lower or "navigation" in msg_lower:
            return NavigationFailed(msg)
        if "closed" in msg_lower or "target" in msg_lower:
            return BrowserClosed(msg)
        # Generic: wrap as BrowserTimeout (most common Playwright error type)
        return BrowserTimeout(msg)
    # Unknown — wrap in BrowserTimeout
    return BrowserTimeout(str(pw_error))


class PlaywrightPage(BrowserPage):
    """Playwright implementation of BrowserPage.

    Wraps a Playwright `Page` object. All errors are translated
    to the BrowserError hierarchy before being raised.
    """

    def __init__(self, pw_page):
        self._page = pw_page
        self._closed = False

    async def goto(self, url: str, timeout: float = 30.0) -> None:
        try:
            await self._page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
        except Exception as e:
            raise _translate_error(e, f"goto({url})")

    async def click(self, selector: Selector, timeout: float = 10.0) -> None:
        try:
            locator = self._page.locator(selector.to_playwright())
            await locator.click(timeout=timeout * 1000)
        except Exception as e:
            raise _translate_error(e, f"click({selector.value})")

    async def fill(self, selector: Selector, value: str, timeout: float = 10.0) -> None:
        try:
            locator = self._page.locator(selector.to_playwright())
            await locator.fill(value, timeout=timeout * 1000)
        except Exception as e:
            raise _translate_error(e, f"fill({selector.value})")

    async def text(self, selector: Selector, timeout: float = 10.0) -> str:
        try:
            locator = self._page.locator(selector.to_playwright())
            return await locator.inner_text(timeout=timeout * 1000)
        except Exception as e:
            raise _translate_error(e, f"text({selector.value})")

    async def exists(self, selector: Selector, timeout: float = 1.0) -> bool:
        try:
            locator = self._page.locator(selector.to_playwright())
            count = await locator.count()
            return count > 0
        except Exception:
            return False

    async def screenshot(self, full_page: bool = False) -> bytes:
        try:
            return await self._page.screenshot(full_page=full_page)
        except Exception as e:
            raise _translate_error(e, "screenshot")

    async def wait_for(self, selector: Selector, timeout: float = 10.0) -> None:
        try:
            locator = self._page.locator(selector.to_playwright())
            await locator.wait_for(timeout=timeout * 1000)
        except Exception as e:
            raise _translate_error(e, f"wait_for({selector.value})")

    async def evaluate(self, expression: str) -> Any:
        try:
            return await self._page.evaluate(expression)
        except Exception as e:
            raise _translate_error(e, "evaluate")

    async def url(self) -> str:
        return self._page.url

    async def title(self) -> str:
        return await self._page.title()
