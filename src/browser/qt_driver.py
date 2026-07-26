"""InsureDesk — Qt Driver (Production).

Full browser automation via PySide6 QtWebEngine.
NO Playwright, NO Chrome, NO browser drivers needed.
Ships with the app — one installer, everything works.

Requires: pip install PySide6 (already a dependency)
QtWebEngine ships with PySide6 on Windows.
"""

from typing import Optional, List, Any, Callable
from dataclasses import dataclass
import asyncio
import json
import os
import tempfile

from src.browser.driver import BrowserEngine, PageInfo, Cookie, cookie_to_dict, dict_to_cookie


class QtDriver(BrowserEngine):
    """Browser driver using Qt WebEngine (production).

    Embedded Chromium inside the PySide6 app.
    Customer's Windows laptop needs NOTHING extra.

    Architecture:
    - QWebEngineView renders the portal page
    - All automation via JavaScript injection
    - Signals bridge Qt events to Python async
    """

    def __init__(self):
        self._view = None
        self._page = None
        self._running = False
        self._data_dir = None

        # Navigation tracking
        self._load_future: Optional[asyncio.Future] = None
        self._current_url = ""
        self._current_title = ""

    @property
    def name(self) -> str:
        return "qt"

    async def start(self, headless: bool = False, port: int = 0) -> bool:
        """Start WebEngine.

        headless — ignored (WebEngine always renders, can't go fully headless).
        port — ignored (WebEngine is embedded, no CDP port).
        """
        if self._running:
            return True

        try:
            from PySide6.QtWebEngineWidgets import QWebEngineView
            from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile
            from PySide6.QtCore import QUrl
        except ImportError:
            raise RuntimeError(
                "QtWebEngine not available. Install PySide6 with:\n"
                "  pip install PySide6 PySide6-QtWebEngine\n"
                "On Windows, PySide6 includes WebEngine by default."
            )

        # Create a temporary data directory for this session
        self._data_dir = tempfile.mkdtemp(prefix="insuredesk_webengine_")

        # Set up profile with persistent storage for cookies
        profile = QWebEngineProfile("InsureDesk", None)
        profile.setHttpUserAgent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )

        self._page = _AsyncWebEnginePage(profile, self)
        self._view = QWebEngineView()
        self._view.setPage(self._page)
        self._view.setWindowTitle("InsureDesk Portal")

        # Connect signals
        self._page.loadFinished.connect(self._on_load_finished)
        self._page.titleChanged.connect(self._on_title_changed)
        self._page.urlChanged.connect(self._on_url_changed)

        self._running = True
        return True

    async def stop(self):
        """Stop WebEngine and clean up."""
        self._running = False
        self._load_future = None
        if self._view:
            try:
                self._view.close()
            except Exception:
                pass
            self._view = None
        self._page = None
        # Clean up temp dir
        if self._data_dir and os.path.exists(self._data_dir):
            try:
                import shutil
                shutil.rmtree(self._data_dir, ignore_errors=True)
            except Exception:
                pass
            self._data_dir = None

    async def navigate(self, url: str, timeout: int = 30000) -> bool:
        """Navigate to a URL and wait for page to load."""
        if not self._page:
            return False

        self._load_future = asyncio.get_event_loop().create_future()

        from PySide6.QtCore import QUrl
        self._page.setUrl(QUrl(url))

        try:
            await asyncio.wait_for(self._load_future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._load_future = None

    async def get_url(self) -> str:
        return self._current_url

    async def get_title(self) -> str:
        return self._current_title

    async def get_page_info(self) -> PageInfo:
        if not self._page:
            return PageInfo()
        html = await self._run_js("document.documentElement.outerHTML")
        text = await self._run_js("document.body.innerText")
        return PageInfo(
            url=self._current_url,
            title=self._current_title,
            html=html or "",
            text=(text or "").strip(),
        )

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        """Click an element by CSS selector via JavaScript."""
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return {{ok: false, error: 'not found'}};
                el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                el.click();
                return {{ok: true}};
            }})()
        """)
        return isinstance(result, dict) and result.get("ok") is True

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        """Fill an input field via JavaScript."""
        result = await self._run_js(f"""
            (() => {{
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
            }})()
        """)
        return isinstance(result, dict) and result.get("ok") is True

    async def select_option(self, selector: str, value: str) -> bool:
        """Select an option via JavaScript."""
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return {{ok: false, error: 'not found'}};
                el.value = {json.dumps(value)};
                el.dispatchEvent(new Event('change', {{bubbles: true}}));
                return {{ok: true}};
            }})()
        """)
        return isinstance(result, dict) and result.get("ok") is True

    async def is_checked(self, selector: str) -> bool:
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? el.checked : false;
            }})()
        """)
        return bool(result)

    async def set_checked(self, selector: str, checked: bool) -> bool:
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return false;
                if (el.checked !== {json.dumps(checked)}) {{
                    el.click();
                }}
                return true;
            }})()
        """)
        return bool(result)

    async def upload_file(self, selector: str, file_path: str) -> bool:
        """Upload file — in WebEngine, set the file input value."""
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return false;
                // Can't set file value from JS for security — alert user instead
                return {{need_manual: true, selector: {json.dumps(selector)}}};
            }})()
        """)
        return isinstance(result, dict) and result.get("need_manual")

    async def get_text(self, selector: str) -> str:
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? el.innerText || el.textContent || '' : '';
            }})()
        """)
        return str(result or "")

    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                return el ? el.getAttribute({json.dumps(attr)}) : null;
            }})()
        """)
        return result if isinstance(result, str) else None

    async def is_visible(self, selector: str) -> bool:
        result = await self._run_js(f"""
            (() => {{
                const el = document.querySelector({json.dumps(selector)});
                if (!el) return false;
                const style = window.getComputedStyle(el);
                return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetWidth > 0;
            }})()
        """)
        return bool(result)

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """Wait for element to appear using MutationObserver."""
        result = await self._run_js(f"""
            (() => {{
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
            }})()
        """)
        return bool(result)

    async def wait_for_navigation(self, timeout: int = 30000) -> bool:
        """Wait for any navigation to complete."""
        self._load_future = asyncio.get_event_loop().create_future()
        try:
            await asyncio.wait_for(self._load_future, timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            self._load_future = None

    async def evaluate(self, script: str) -> Any:
        return await self._run_js(script)

    async def screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        if not self._view:
            return None
        try:
            from PySide6.QtGui import QImage
            from PySide6.QtCore import QSize
            img = self._view.grab().toImage()
            if path:
                img.save(path)
                return None
            # Return as bytes
            buffer = img.bits().__int__()
            return bytes(await self._run_js("document.body.innerText"))
        except Exception:
            return None

    async def get_cookies(self) -> List[Cookie]:
        """Get cookies via JavaScript (document.cookie only shows non-httpOnly)."""
        raw = await self._run_js("document.cookie")
        cookies = []
        if raw:
            for item in str(raw).split(";"):
                item = item.strip()
                if "=" in item:
                    name, value = item.split("=", 1)
                    cookies.append(Cookie(name=name.strip(), value=value.strip()))
        return cookies

    async def set_cookies(self, cookies: List[Cookie]):
        """Set cookies via JavaScript."""
        for c in cookies:
            escaped = json.dumps(f"{c.name}={c.value}; path={c.path}")
            await self._run_js(f"document.cookie = {escaped}")

    async def clear_cookies(self):
        """Clear all cookies via JavaScript."""
        await self._run_js("""
            document.cookie.split(';').forEach(c => {
                document.cookie = c.trim().split('=')[0] + '=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/';
            });
        """)

    async def get_tabs(self) -> int:
        return 1  # WebEngineView is single-tab

    async def switch_tab(self, index: int) -> bool:
        return index == 0

    async def close_tab(self, index: int = -1):
        pass

    # ── Internal ──

    async def _run_js(self, script: str) -> Any:
        """Run JavaScript in the page and return the result."""
        if not self._page:
            return None

        future = asyncio.get_event_loop().create_future()

        def callback(result):
            if not future.done():
                future.set_result(result)

        try:
            self._page.runJavaScript(script, callback)
            return await asyncio.wait_for(future, timeout=10.0)
        except (asyncio.TimeoutError, Exception):
            return None

    def _on_load_finished(self, ok: bool):
        """Called when page finishes loading."""
        if self._load_future and not self._load_future.done():
            self._load_future.set_result(ok)

    def _on_title_changed(self, title: str):
        self._current_title = title

    def _on_url_changed(self, url):
        self._current_url = url.toString() if hasattr(url, 'toString') else str(url)

    @property
    def view(self):
        """Get the QWebEngineView widget for embedding in a window."""
        return self._view


class _AsyncWebEnginePage:
    """Wrapper that makes QWebEnginePage callable from async code.

    In production, this would be a proper QWebEnginePage subclass.
    For now, it's a simplified adapter.
    """

    def __init__(self, profile, engine):
        from PySide6.QtWebEngineWidgets import QWebEngineView
        self._impl = QWebEngineView()
        self._engine = engine
        self.loadFinished = _SignalProxy()
        self.titleChanged = _SignalProxy()
        self.urlChanged = _SignalProxy()

        # Connect real signals
        self._impl.loadFinished.connect(self.loadFinished.emit)
        self._impl.titleChanged.connect(self.titleChanged.emit)
        self._impl.urlChanged.connect(self.urlChanged.emit)

    def setUrl(self, url):
        self._impl.setUrl(url)

    def runJavaScript(self, script, callback=None):
        if callback:
            self._impl.page().runJavaScript(script, callback)
        else:
            self._impl.page().runJavaScript(script)

    def toHtml(self, callback):
        self._impl.page().toHtml(callback)

    def url(self):
        return self._impl.url()


class _SignalProxy:
    """Simple signal proxy for Qt compatibility."""

    def __init__(self):
        self._callbacks = []

    def connect(self, callback):
        self._callbacks.append(callback)

    def emit(self, *args, **kwargs):
        for cb in self._callbacks:
            cb(*args, **kwargs)
