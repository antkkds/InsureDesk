"""ChromeCDPDriver — production browser driver using Chrome DevTools Protocol.

Connects to a Chrome instance via CDP WebSocket.
All portal automation is done via JavaScript injection (Runtime.evaluate)
and direct CDP commands where needed (screenshots, cookies, navigation).

No Playwright, no QtWebEngine required.
Ships with PyInstaller .exe — one dependency: websockets.
"""

import asyncio
import json
import os
from typing import Optional, List, Any

from src.browser.driver import BrowserEngine, PageInfo, Cookie, cookie_to_dict, dict_to_cookie
from src.browser.chrome.connection import CdpConnection
from src.browser.chrome.launcher import ChromeLauncher
from src.browser.chrome.manager import ChromeManager
from src.browser.chrome.tabs import list_tabs, find_tab_by_domain, create_tab, activate_tab, TabInfo


class ChromeCDPDriver(BrowserEngine):
    """Production browser driver using Chrome DevTools Protocol.

    Connects to a Chrome instance (auto-launched or existing) via CDP WebSocket.
    All DOM operations use JavaScript injection for reliability.

    Usage:
        driver = ChromeCDPDriver()
        await driver.start(port=9222)
        await driver.navigate("https://www.greateasternlife.com")
        await driver.fill("#username", "agent@example.com")
        await driver.click("#login-btn")
    """

    def __init__(self):
        self._conn: Optional[CdpConnection] = None
        self._tab: Optional[TabInfo] = None
        self._port = 0
        self._running = False
        self._domains_enabled = False
        self._manager: Optional[ChromeManager] = None

    @property
    def name(self) -> str:
        return "chrome"

    async def start(self, headless: bool = False, port: int = 0) -> bool:
        """Start the ChromeCDPDriver.

        Auto-launches Chrome with CDP enabled (via ChromeManager)
        if Chrome is not already running on the CDP port.

        Args:
            headless: If True, run in headless mode.
            port: CDP port (default: 0 = auto-select free port).

        Returns:
            True if connected successfully.
        """
        if self._running:
            return True

        # Use ChromeManager to ensure Chrome is running
        self._manager = ChromeManager(port=port or 0)
        await self._manager.start()
        self._port = self._manager.port

        # Get page targets and find a suitable tab
        tabs = list_tabs(self._port)
        if not tabs:
            # Create a blank tab
            tab_info = create_tab(self._port, "about:blank")
            if not tab_info:
                raise RuntimeError("Failed to create Chrome tab")
            self._tab = tab_info
        else:
            self._tab = tabs[0]

        # Bring tab to foreground
        activate_tab(self._port, self._tab.id)

        # Connect to the page via WebSocket
        self._conn = CdpConnection()
        await self._conn.connect(self._tab.ws_url)

        # Enable necessary CDP domains
        await self._enable_domains()

        self._running = True
        return True

    async def _enable_domains(self):
        """Enable CDP domains needed for automation."""
        if self._domains_enabled:
            return
        try:
            await self._conn.send_command("Page.enable", timeout=5)
            await self._conn.send_command("Runtime.enable", timeout=5)
            await self._conn.send_command("Network.enable", timeout=5)
            self._domains_enabled = True
        except Exception:
            pass

    async def stop(self):
        """Disconnect from Chrome and release resources."""
        self._running = False
        self._domains_enabled = False
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass
            self._conn = None
        self._tab = None
        if self._manager:
            try:
                await self._manager.stop()
            except Exception:
                pass
            self._manager = None

    async def navigate(self, url: str, timeout: int = 30000) -> bool:
        """Navigate to a URL and wait for page load.

        Uses CDP Page.navigate + Page.frameStoppedLoading event.
        Falls back to timeout-based wait.
        """
        if not self._conn:
            return False

        # Set up navigation wait
        nav_future = asyncio.get_event_loop().create_future()

        def on_frame_stopped(params):
            if not nav_future.done():
                nav_future.set_result(True)

        self._conn.on("Page.frameStoppedLoading", on_frame_stopped)

        try:
            result = await self._conn.send_command("Page.navigate", {"url": url}, timeout=15)
            if "error" in str(result).lower():
                return False

            # Wait for navigation to complete
            try:
                await asyncio.wait_for(nav_future, timeout=timeout / 1000)
                return True
            except asyncio.TimeoutError:
                return False
        except Exception:
            return False
        finally:
            self._conn.off("Page.frameStoppedLoading", on_frame_stopped)

    async def get_url(self) -> str:
        """Get the current page URL via JavaScript."""
        result = await self._eval_js("window.location.href")
        return str(result or "")

    async def get_title(self) -> str:
        """Get the current page title via JavaScript."""
        result = await self._eval_js("document.title")
        return str(result or "")

    async def get_page_info(self) -> PageInfo:
        """Get full page info via JavaScript."""
        result = await self._eval_js("""(() => ({
            url: window.location.href,
            title: document.title,
            html: document.documentElement.outerHTML,
            text: document.body ? document.body.innerText : ''
        }))()""")
        if isinstance(result, dict):
            return PageInfo(
                url=result.get("url", ""),
                title=result.get("title", ""),
                html=result.get("html", ""),
                text=result.get("text", "").strip(),
            )
        return PageInfo()

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        """Click an element identified by CSS selector via JavaScript."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ok: false, error: 'not found'}};
            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
            el.click();
            return {{ok: true}};
        }})()""")
        return isinstance(result, dict) and result.get("ok") is True

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        """Type text into an input field via JavaScript."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ok: false, error: 'not found'}};
            el.focus();
            el.select();
            // Use native input setter to trigger React/Angular change detection
            const nativeSetter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            );
            if (nativeSetter && nativeSetter.set) {{
                nativeSetter.set.call(el, {json.dumps(value)});
            }} else {{
                el.value = {json.dumps(value)};
            }}
            el.dispatchEvent(new Event('input', {{bubbles: true}}));
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            el.blur();
            return {{ok: true}};
        }})()""")
        return isinstance(result, dict) and result.get("ok") is True

    async def select_option(self, selector: str, value: str) -> bool:
        """Select an option from a dropdown via JavaScript."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return {{ok: false, error: 'not found'}};
            el.value = {json.dumps(value)};
            el.dispatchEvent(new Event('change', {{bubbles: true}}));
            return {{ok: true}};
        }})()""")
        return isinstance(result, dict) and result.get("ok") is True

    async def is_checked(self, selector: str) -> bool:
        """Check if a checkbox/radio is checked."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            return el ? el.checked : false;
        }})()""")
        return bool(result)

    async def set_checked(self, selector: str, checked: bool) -> bool:
        """Check or uncheck a checkbox/radio."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return false;
            if (el.checked !== {json.dumps(checked)}) {{
                el.click();
            }}
            return true;
        }})()""")
        return bool(result)

    async def upload_file(self, selector: str, file_path: str) -> bool:
        """Upload a file via file input.

        CDP can set file input values via DOM.setFileInputFiles.
        """
        if not self._conn:
            return False

        if not os.path.isfile(file_path):
            return False

        try:
            # First get the element node
            node_result = await self._eval_js(f"""(() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return null;
                // Get backend node ID for CDP
                return el.__cdp_node_id;
            }})()""")

            # Use CDP to set file
            abs_path = os.path.abspath(file_path)
            await self._conn.send_command(
                "DOM.setFileInputFiles",
                {
                    "files": [abs_path],
                    "nodeId": 0,  # We'll use the CSS selector approach
                },
                timeout=10,
            )
            return True
        except Exception:
            # Fallback: set via JS (may not work in all cases)
            result = await self._eval_js(f"""(() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return {{ok: false, error: 'not found'}};
                // CDP handles file upload, not JS
                return {{ok: false, need_cdp: true}};
            }})()""")
            return False

    async def get_text(self, selector: str) -> str:
        """Get visible text content of an element."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            return el ? el.innerText || el.textContent || '' : '';
        }})()""")
        return str(result or "")

    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        """Get an attribute value of an element."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            return el ? el.getAttribute({json.dumps(attr)}) : null;
        }})()""")
        return result if isinstance(result, str) else None

    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible."""
        result = await self._eval_js(f"""(() => {{
            const el = document.querySelector({json.dumps(selector)});
            if (!el) return false;
            const style = window.getComputedStyle(el);
            return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetWidth > 0;
        }})()""")
        return bool(result)

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """Wait for an element to appear using JavaScript MutationObserver."""
        result = await self._eval_js(f"""(() => {{
            return new Promise((resolve) => {{
                if (document.querySelector({json.dumps(selector)})) {{
                    resolve(true);
                    return;
                }}
                const observer = new MutationObserver(() => {{
                    if (document.querySelector({json.dumps(selector)})) {{
                        observer.disconnect();
                        resolve(true);
                    }}
                }});
                observer.observe(document.body, {{childList: true, subtree: true}});
                setTimeout(() => {{ observer.disconnect(); resolve(false); }}, {timeout});
            }});
        }})()""")
        return bool(result)

    async def wait_for_navigation(self, timeout: int = 30000) -> bool:
        """Wait for page navigation to complete."""
        if not self._conn:
            return False

        nav_future = asyncio.get_event_loop().create_future()

        def on_frame_stopped(params):
            if not nav_future.done():
                nav_future.set_result(True)

        self._conn.on("Page.frameStoppedLoading", on_frame_stopped)
        try:
            await asyncio.wait_for(nav_future, timeout=timeout / 1000)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._conn.off("Page.frameStoppedLoading", on_frame_stopped)

    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript in the page context and return the result."""
        return await self._eval_js(script)

    async def screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        """Take a screenshot via CDP Page.captureScreenshot.

        Args:
            path: If given, save screenshot to this path.

        Returns:
            PNG bytes if no path given, None otherwise.
        """
        if not self._conn:
            return None

        try:
            result = await self._conn.send_command(
                "Page.captureScreenshot", {"format": "png"}, timeout=15
            )
            data = result.get("data", "")
            if not data:
                return None

            import base64
            img_bytes = base64.b64decode(data)

            if path:
                os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
                with open(path, "wb") as f:
                    f.write(img_bytes)
                return None

            return img_bytes
        except Exception:
            return None

    async def get_cookies(self) -> List[Cookie]:
        """Get all cookies via CDP Network.getCookies."""
        if not self._conn:
            return []

        try:
            result = await self._conn.send_command("Network.getCookies", timeout=10)
            raw_cookies = result.get("cookies", [])
            cookies = []
            for c in raw_cookies:
                cookies.append(Cookie(
                    name=c.get("name", ""),
                    value=c.get("value", ""),
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                    secure=c.get("secure", False),
                    http_only=c.get("httpOnly", False),
                    same_site=c.get("sameSite", "Lax"),
                    expires=int(c.get("expires", 0)),
                ))
            return cookies
        except Exception:
            return []

    async def set_cookies(self, cookies: List[Cookie]):
        """Set cookies via CDP Network.setCookie."""
        if not self._conn:
            return

        for c in cookies:
            try:
                params = {
                    "name": c.name,
                    "value": c.value,
                    "domain": c.domain,
                    "path": c.path,
                }
                if c.secure:
                    params["secure"] = True
                if c.http_only:
                    params["httpOnly"] = True
                if c.same_site:
                    params["sameSite"] = c.same_site
                await self._conn.send_command_no_wait("Network.setCookie", params)
            except Exception:
                pass

    async def clear_cookies(self):
        """Clear all cookies via CDP Network.clearBrowserCookies."""
        if not self._conn:
            return
        try:
            await self._conn.send_command_no_wait("Network.clearBrowserCookies")
        except Exception:
            pass

    async def get_tabs(self) -> int:
        """Get number of open tabs in Chrome."""
        return len(list_tabs(self._port))

    async def switch_tab(self, index: int) -> bool:
        """Switch to a specific tab by index.

        This reconnects the WebSocket to the new tab.
        """
        tabs = list_tabs(self._port)
        if index < 0 or index >= len(tabs):
            return False

        tab = tabs[index]

        # Close existing connection
        if self._conn:
            try:
                await self._conn.close()
            except Exception:
                pass

        # Activate tab
        activate_tab(self._port, tab.id)

        # Connect to new tab
        self._tab = tab
        self._conn = CdpConnection()
        await self._conn.connect(tab.ws_url)
        await self._enable_domains()
        return True

    async def close_tab(self, index: int = -1):
        """Close a tab (-1 = current tab)."""
        from src.browser.chrome.tabs import close_tab as _close_tab

        if index == -1 and self._tab:
            _close_tab(self._port, self._tab.id)
            self._tab = None
            self._running = False
        elif index >= 0:
            tabs = list_tabs(self._port)
            if index < len(tabs):
                _close_tab(self._port, tabs[index].id)

    # ── Internal ──

    async def _eval_js(self, script: str) -> Any:
        """Execute JavaScript via CDP Runtime.evaluate and return the result value.

        Handles serialization of return values.
        """
        if not self._conn:
            return None

        try:
            result = await self._conn.send_command(
                "Runtime.evaluate",
                {
                    "expression": script,
                    "returnByValue": True,
                    "awaitPromise": True,
                    "userGesture": True,
                },
                timeout=30,
            )

            if "exceptionDetails" in result:
                return None

            value = result.get("result", {}).get("value")
            return value
        except Exception:
            return None

    @property
    def tab(self) -> Optional[TabInfo]:
        """Get the currently attached tab info."""
        return self._tab

    @property
    def connection(self) -> Optional[CdpConnection]:
        """Get the underlying CDP connection."""
        return self._conn

    @property
    def is_connected(self) -> bool:
        """Check if the CDP connection is active."""
        return self._conn is not None and self._conn.is_connected
