"""InsureDesk Drivers — CDP Page Implementation.

Implements BrowserPage using Chrome DevTools Protocol directly.
No Playwright needed — pure WebSocket + CDP commands.
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from src.runtime.browser_session import (
    BrowserPage,
    Selector,
    BrowserTimeout,
    ElementNotFound,
    NavigationFailed,
    BrowserClosed,
)


class CdpPage(BrowserPage):
    """A browser page controlled via Chrome DevTools Protocol.

    Uses a CdpConnection for low-level CDP WebSocket communication.
    DOM operations are done via JavaScript injection (Runtime.evaluate)
    for maximum reliability across portal types.
    """

    def __init__(self, conn, tab_id: str, tab_url: str = ""):
        self._conn = conn
        self._tab_id = tab_id
        self._current_url = tab_url
        self._closed = False

    async def goto(self, url: str, timeout: float = 30.0) -> None:
        try:
            result = await self._conn.send_command(
                "Page.navigate", {"url": url}, timeout=timeout
            )
            if result.get("errorText"):
                raise NavigationFailed(
                    f"Navigation to {url} failed: {result['errorText']}"
                )
            self._current_url = result.get("url", url)
        except NavigationFailed:
            raise
        except Exception as e:
            raise NavigationFailed(str(e))

    async def click(self, selector: Selector, timeout: float = 10.0) -> None:
        js = self._build_click_js(selector)
        result = await self._evaluate_js(js, timeout)
        if result is None or result is False:
            raise ElementNotFound(f"Element {selector.value} not clickable")

    async def fill(self, selector: Selector, value: str, timeout: float = 10.0) -> None:
        js = self._build_fill_js(selector, value)
        result = await self._evaluate_js(js, timeout)
        if result is None or result is False:
            raise ElementNotFound(f"Element {selector.value} not found for fill")

    async def text(self, selector: Selector, timeout: float = 10.0) -> str:
        js = self._build_text_js(selector)
        result = await self._evaluate_js(js, timeout)
        return str(result) if result is not None else ""

    async def exists(self, selector: Selector, timeout: float = 1.0) -> bool:
        js = self._build_exists_js(selector)
        result = await self._evaluate_js(js, timeout)
        return bool(result)

    async def screenshot(self, full_page: bool = False) -> bytes:
        try:
            params = {"format": "png"}
            if full_page:
                # Get full page dimensions
                metrics = await self._conn.send_command("Page.getLayoutMetrics")
                content_size = metrics.get("contentSize", {})
                params.update({
                    "clip": {
                        "x": 0, "y": 0,
                        "width": content_size.get("width", 1920),
                        "height": content_size.get("height", 1080),
                        "scale": 1,
                    }
                })
            result = await self._conn.send_command("Page.captureScreenshot", params)
            data = result.get("data", "")
            return base64.b64decode(data)
        except Exception as e:
            from src.runtime.browser_session import BrowserError
            raise BrowserError(f"Screenshot failed: {e}")

    async def wait_for(self, selector: Selector, timeout: float = 10.0) -> None:
        js = self._build_wait_js(selector, timeout)
        result = await self._evaluate_js(js, timeout)
        if not result:
            raise BrowserTimeout(
                f"Element {selector.value} not visible within {timeout}s"
            )

    async def evaluate(self, expression: str) -> Any:
        try:
            result = await self._conn.send_command(
                "Runtime.evaluate", {
                    "expression": expression,
                    "returnByValue": True,
                }
            )
            return result.get("result", {}).get("value")
        except Exception as e:
            return None

    async def url(self) -> str:
        try:
            result = await self._conn.send_command(
                "Runtime.evaluate", {
                    "expression": "window.location.href",
                    "returnByValue": True,
                }
            )
            val = result.get("result", {}).get("value")
            if val:
                self._current_url = str(val)
        except Exception:
            pass
        return self._current_url

    async def title(self) -> str:
        try:
            result = await self._conn.send_command(
                "Runtime.evaluate", {
                    "expression": "document.title",
                    "returnByValue": True,
                }
            )
            return str(result.get("result", {}).get("value", ""))
        except Exception:
            return ""

    # ── Internal: JS builders ──

    def _build_selector_js(self, selector: Selector) -> str:
        """Build a JavaScript query selector string."""
        mapping = {
            "css": lambda v: f'document.querySelector("{v}")',
            "id": lambda v: f'document.getElementById("{v}")',
            "testid": lambda v: f'document.querySelector(\'[data-testid="{v}"]\')',
            "xpath": lambda v: f'document.evaluate("{v}", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue',
            "text": lambda v: f'Array.from(document.querySelectorAll("button,a,span,label")).find(el => el.textContent.trim() === "{v}")',
        }
        return mapping.get(selector.strategy, mapping["css"])(selector.value)

    def _build_click_js(self, selector: Selector) -> str:
        el = self._build_selector_js(selector)
        return f"""
            (() => {{
                const el = {el};
                if (!el) return false;
                el.scrollIntoView({{block:'center'}});
                el.click();
                return true;
            }})()
        """

    def _build_fill_js(self, selector: Selector, value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace("'", "\\'")
        el = self._build_selector_js(selector)
        return f"""
            (() => {{
                const el = {el};
                if (!el) return false;
                el.focus();
                el.value = '';
                el.value = '{escaped}';
                el.dispatchEvent(new Event('input', {{bubbles:true}}));
                el.dispatchEvent(new Event('change', {{bubbles:true}}));
                return true;
            }})()
        """

    def _build_text_js(self, selector: Selector) -> str:
        el = self._build_selector_js(selector)
        return f"""
            (() => {{
                const el = {el};
                return el ? el.textContent.trim() || el.value || '' : '';
            }})()
        """

    def _build_exists_js(self, selector: Selector) -> str:
        el = self._build_selector_js(selector)
        return f"!!({el})"

    def _build_wait_js(self, selector: Selector, timeout_s: float) -> str:
        el = self._build_selector_js(selector)
        return f"""
            (() => {{
                const start = Date.now();
                const timeout = {int(timeout_s * 1000)};
                while (Date.now() - start < timeout) {{
                    if ({el}) return true;
                }}
                return !!({el});
            }})()
        """

    async def _evaluate_js(self, js: str, timeout: float = 10.0) -> Any:
        """Execute JavaScript via CDP Runtime.evaluate."""
        try:
            result = await self._conn.send_command(
                "Runtime.evaluate", {
                    "expression": js,
                    "returnByValue": True,
                    "awaitPromise": True,
                },
                timeout=timeout,
            )
            return result.get("result", {}).get("value")
        except Exception:
            return None
