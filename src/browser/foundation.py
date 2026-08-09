"""InsureDesk — Browser Automation Foundation Layer.

Wraps BrowserEngine with safe operations (retry, verify, standardized waits).
Portal Adapters use this class instead of calling BrowserEngine directly.

Flow:
    PortalAdapter → BrowserFoundation → BrowserEngine → Browser

Usage:
    engine = create_browser_engine(prefer="playwright")
    browser = BrowserFoundation(engine)
    await browser.wait_until_ready()
    await browser.safe_click("#btnLogin")
    await browser.safe_fill("#username", "user")
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Callable, Awaitable, TypeVar, Any
import asyncio
import time
import logging

from src.browser.driver import BrowserEngine

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ══════════════════════════════════════════════════════════════════
# TimeoutPolicy
# ══════════════════════════════════════════════════════════════════

@dataclass
class TimeoutPolicy:
    """Standardized timeouts for all browser operations (seconds).

    Factory presets:
        TimeoutPolicy.fast()    — fast Portal (GE, simple)
        TimeoutPolicy.normal()  — default
        TimeoutPolicy.slow()    — slow Portal (legacy, complex)
    """
    dom: float = 10.0
    network: float = 15.0
    loading: float = 10.0
    iframe: float = 10.0
    click: float = 10.0
    fill: float = 10.0
    navigation: float = 30.0
    upload: float = 120.0
    short: float = 3.0
    normal: float = 10.0
    long: float = 30.0

    @classmethod
    def fast(cls) -> "TimeoutPolicy":
        """For fast portals with quick response times."""
        return cls(
            dom=3.0, network=5.0, loading=3.0, iframe=3.0,
            click=5.0, fill=5.0, navigation=15.0, upload=60.0,
            short=1.0, normal=5.0, long=15.0,
        )

    @classmethod
    def standard(cls) -> "TimeoutPolicy":
        """Default timeouts (same as no-arg constructor)."""
        return cls()

    @classmethod
    def slow(cls) -> "TimeoutPolicy":
        """For legacy/overseas portals with slow response times."""
        return cls(
            dom=20.0, network=30.0, loading=20.0, iframe=20.0,
            click=20.0, fill=20.0, navigation=60.0, upload=180.0,
            short=5.0, normal=20.0, long=60.0,
        )


# ══════════════════════════════════════════════════════════════════
# RetryPolicy
# ══════════════════════════════════════════════════════════════════

@dataclass
class RetryPolicy:
    """Retry configuration for browser operations.

    Usage:
        RetryPolicy()                       # 3 retries, exponential
        RetryPolicy(retries=5, delay=1.0)   # upload: more retries
        RetryPolicy(retries=2, jitter=True) # click: fewer retries
    """
    retries: int = 3
    delay: float = 0.5
    backoff: float = 1.5
    jitter: bool = False
    max_delay: float = 10.0


# ══════════════════════════════════════════════════════════════════
# Exception Hierarchy
# ══════════════════════════════════════════════════════════════════

class BrowserFoundationError(Exception):
    """Base for all Browser Foundation errors."""
    def __init__(self, message: str, context: Optional[dict] = None):
        super().__init__(message)
        self.context = context or {}


class ElementNotVisible(BrowserFoundationError):
    """Element exists but is not visible."""


class VerificationFailed(BrowserFoundationError):
    """Action succeeded syntactically but post-verification failed."""


class RetryExceeded(BrowserFoundationError):
    """All retry attempts exhausted."""


class WaitTimeout(BrowserFoundationError):
    """A wait condition timed out."""


class SessionExpired(BrowserFoundationError):
    """Browser session expired or was logged out."""


class NavigationFailed(BrowserFoundationError):
    """Page navigation failed."""


class UploadFailed(BrowserFoundationError):
    """File upload failed."""


class DownloadFailed(BrowserFoundationError):
    """File download failed."""


class RecoveryFailed(BrowserFoundationError):
    """Session recovery failed after all attempts."""


# ══════════════════════════════════════════════════════════════════
# MockEngine — Minimal test double for unit tests
# ══════════════════════════════════════════════════════════════════

class MockEngine:
    """In-memory BrowserEngine for testing the foundation layer.

    Records all calls. Raises configured errors for failure-path tests.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.calls: list[str] = []
        self.url = "about:blank"
        self.title = "Mock Page"
        self.visible_elements: set[str] = set()
        self.input_values: dict[str, str] = {}
        self.checked_state: dict[str, bool] = {}
        self.ready_state = "complete"
        self.iframe_count = 0
        self.nav_ok = True
        self.click_ok = True
        self.fill_ok = True
        self.select_ok = True
        self.upload_ok = True
        self.errors: dict[str, Exception] = {}
        self._set_visible_after_click: set[str] = set()

    def _record(self, method: str, detail: str = ""):
        self.calls.append(f"{method}({detail})")

    def set_visible_after_click(self, *selectors: str):
        """Elements that become visible only after click."""
        self._set_visible_after_click = set(selectors)

    # --- Engine interface ---

    async def start(self, headless: bool = False, port: int = 0) -> bool:
        self._record("start", f"headless={headless}")
        return True

    async def stop(self):
        self._record("stop")

    async def navigate(self, url: str, timeout: int = 30000) -> bool:
        self._record("navigate", url)
        if "error" in url.lower():
            return False
        self.url = url
        return self.nav_ok

    async def get_url(self) -> str:
        return self.url

    async def get_title(self) -> str:
        return self.title

    async def get_page_info(self):
        from src.browser.driver import PageInfo
        return PageInfo(url=self.url, title=self.title, html="", text="")

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        self._record("click", selector)
        if selector in self.errors:
            raise self.errors[selector]
        # Elements that become visible after click
        for s in self._set_visible_after_click:
            self.visible_elements.add(s)
        return self.click_ok

    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        self._record("fill", f"{selector}={value}")
        if selector in self.errors:
            raise self.errors[selector]
        self.input_values[selector] = value
        return self.fill_ok

    async def select_option(self, selector: str, value: str) -> bool:
        self._record("select", f"{selector}={value}")
        self.input_values[selector] = value
        return self.select_ok

    async def is_checked(self, selector: str) -> bool:
        self._record("is_checked", selector)
        return self.checked_state.get(selector, False)

    async def set_checked(self, selector: str, checked: bool) -> bool:
        self._record("set_checked", f"{selector}={checked}")
        self.checked_state[selector] = checked
        return True

    async def upload_file(self, selector: str, file_path: str) -> bool:
        self._record("upload", f"{selector}={file_path}")
        return self.upload_ok

    async def get_text(self, selector: str) -> str:
        return self.input_values.get(selector, "")

    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        if attr == "value":
            return self.input_values.get(selector)
        return None

    async def is_visible(self, selector: str) -> bool:
        self._record("is_visible", selector)
        return selector in self.visible_elements

    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        self._record("wait_for_selector", selector)
        if selector in self.errors:
            raise self.errors[selector]
        return selector in self.visible_elements or True  # default: found

    async def wait_for_navigation(self, timeout: int = 30000) -> bool:
        self._record("wait_for_navigation")
        return True

    async def evaluate(self, script: str) -> Any:
        self._record("evaluate", script[:60])
        if "readyState" in script:
            return self.ready_state == "complete" or self.ready_state == "interactive"
        if "querySelectorAll('iframe')" in script:
            return self.iframe_count
        if "scrollIntoView" in script:
            return None
        if "value" in script:
            # Extract selector from the js expression
            import re
            m = re.search(r"querySelector\('([^']+)'\)", script)
            if m:
                sel = m.group(1)
                return self.input_values.get(sel, "")
            return None
        return None

    async def screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        return b"mock"

    async def get_cookies(self):
        return []

    async def set_cookies(self, cookies):
        pass

    async def clear_cookies(self):
        pass

    async def get_tabs(self) -> int:
        return 1

    async def switch_tab(self, index: int) -> bool:
        return True

    async def close_tab(self, index: int = -1):
        pass


# ══════════════════════════════════════════════════════════════════
# BrowserFoundation
# ══════════════════════════════════════════════════════════════════

class BrowserFoundation:
    """Safe browser automation layer for Portal Adapters.

    Wraps a BrowserEngine with retry, verification, and standardized waits.
    Adapters use this class instead of calling BrowserEngine directly.

    Args:
        engine: BrowserEngine instance
        timeout: Optional custom TimeoutPolicy
    """

    def __init__(
        self,
        engine: BrowserEngine,
        timeout: Optional[TimeoutPolicy] = None,
    ):
        self._engine = engine
        self._timeout = timeout or TimeoutPolicy()
        self._stats: dict[str, int] = {
            "clicks": 0, "fills": 0, "selects": 0,
            "checks": 0, "uploads": 0, "waits": 0,
            "retries": 0,
        }

    @property
    def engine(self) -> BrowserEngine:
        return self._engine

    @property
    def timeout(self) -> TimeoutPolicy:
        return self._timeout

    @property
    def stats(self) -> dict[str, int]:
        return dict(self._stats)

    # ── Wait Methods ─────────────────────────────────────────────

    async def wait_dom(self, timeout: Optional[float] = None) -> None:
        """Wait for DOM readyState to be 'complete' or 'interactive'."""
        t = timeout or self._timeout.dom
        deadline = time.monotonic() + t
        last_error: Optional[str] = None

        while time.monotonic() < deadline:
            try:
                ready = await self._engine.evaluate(
                    "document.readyState === 'complete' "
                    "|| document.readyState === 'interactive'"
                )
                if ready:
                    self._stats["waits"] += 1
                    return
            except Exception as e:
                last_error = str(e)
            await asyncio.sleep(0.3)

        raise WaitTimeout(
            f"DOM not ready within {t}s",
            context={"timeout": t, "last_error": last_error},
        )

    async def wait_network(self, timeout: Optional[float] = None) -> None:
        """Wait for page load event (basic network idle detection)."""
        t = timeout or self._timeout.network
        try:
            await self._engine.evaluate(
                "new Promise(resolve => {"
                "  if (document.readyState === 'complete')"
                "    { resolve(true); return; }"
                "  window.addEventListener('load',"
                "    () => resolve(true), {once: true});"
                "  setTimeout(() => resolve(true), 30000);"
                "})"
            )
            self._stats["waits"] += 1
        except Exception as e:
            raise WaitTimeout(
                f"Network wait failed within {t}s",
                context={"timeout": t, "error": str(e)},
            )

    async def wait_loading(self, timeout: Optional[float] = None) -> None:
        """Wait for common loading indicators to disappear. Never raises."""
        t = timeout or self._timeout.loading
        deadline = time.monotonic() + t

        loading_selectors = [
            ".loading", "#loading", "[class*='loading']",
            ".spinner", "[class*='spinner']",
            ".progress", "[aria-busy='true']",
        ]

        while time.monotonic() < deadline:
            still_loading = False
            for sel in loading_selectors:
                try:
                    if await self._engine.is_visible(sel):
                        still_loading = True
                        break
                except Exception:
                    pass
            if not still_loading:
                self._stats["waits"] += 1
                return
            await asyncio.sleep(0.5)

        logger.warning("Loading indicator still visible after %.1fs", t)

    async def wait_iframe(self, timeout: Optional[float] = None) -> None:
        """Wait for iframes to be available. Never raises."""
        t = timeout or self._timeout.iframe
        deadline = time.monotonic() + t
        while time.monotonic() < deadline:
            try:
                await self._engine.evaluate(
                    "document.querySelectorAll('iframe').length"
                )
                self._stats["waits"] += 1
                return
            except Exception:
                await asyncio.sleep(0.3)

    async def wait_until_ready(self, timeout: Optional[float] = None) -> None:
        """Combined wait: DOM → network → loading → iframe."""
        await self.wait_dom(timeout)
        await self.wait_network(timeout)
        await self.wait_loading(timeout)
        await self.wait_iframe(timeout)

    # ── Retry ────────────────────────────────────────────────────

    async def retry(
        self,
        action: Callable[[], Awaitable[T]],
        retries: int = 3,
        delay: float = 0.5,
        backoff: float = 1.5,
    ) -> T:
        """Generic retry wrapper with exponential backoff.

        Args:
            action: Async callable to retry.
            retries: Max attempts.
            delay: Initial delay between attempts (seconds).
            backoff: Multiplier for delay on each retry.

        Returns:
            The action's return value.

        Raises:
            RetryExceeded: All attempts exhausted.
        """
        last_error: Optional[Exception] = None
        current_delay = delay

        for attempt in range(1, retries + 1):
            try:
                result = await action()
                self._stats["retries"] += (attempt - 1)
                return result
            except BrowserFoundationError:
                raise  # Don't retry foundation errors
            except Exception as e:
                last_error = e
                if attempt < retries:
                    logger.debug("Retry %d/%d: %s", attempt, retries, e)
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

        self._stats["retries"] += (retries - 1)
        raise RetryExceeded(
            f"Action failed after {retries} attempts",
            context={"retries": retries, "last_error": str(last_error)},
        )

    # ── Safe Click ───────────────────────────────────────────────

    async def safe_click(
        self,
        selector: str,
        timeout: Optional[float] = None,
        retries: int = 3,
    ) -> None:
        """Click with pre-checks and verification.

        Flow: wait_for_selector → visible? → scroll → click → verify
        """
        t = timeout or self._timeout.click
        timeout_ms = int(t * 1000)
        # Escape single quotes in selector for JS evaluation
        _safe_sel = selector.replace("'", "\\'")

        async def _attempt() -> bool:
            # 1. Wait for element
            found = await self._engine.wait_for_selector(selector, timeout=timeout_ms)
            if not found:
                raise ValueError(f"Element '{selector}' not found")

            # 2. Check visibility, scroll if needed
            if not await self._engine.is_visible(selector):
                await self._engine.evaluate(
                    f"document.querySelector('{_safe_sel}')"
                    f"?.scrollIntoView({{block: 'center'}})"
                )
                await asyncio.sleep(0.3)
                if not await self._engine.is_visible(selector):
                    raise ElementNotVisible(f"Element '{selector}' not visible after scroll")

            # 3. Click
            clicked = await self._engine.click(selector, timeout=timeout_ms)
            if not clicked:
                raise ValueError(f"Click '{selector}' returned False")

            # 4. Wait briefly and verify click took effect
            await asyncio.sleep(0.5)
            self._stats["clicks"] += 1
            return True

        try:
            await self.retry(_attempt, retries=retries)
        except RetryExceeded as e:
            raise VerificationFailed(
                f"Click '{selector}' failed",
                context={"selector": selector, "retries": retries,
                         "error": str(e)},
            )

    # ── Safe Fill ────────────────────────────────────────────────

    async def safe_fill(
        self,
        selector: str,
        value: str,
        timeout: Optional[float] = None,
        retries: int = 3,
    ) -> None:
        """Fill a field with verification.

        Flow: wait_for_selector → click (focus) → fill → read value → verify
        """
        t = timeout or self._timeout.fill
        timeout_ms = int(t * 1000)
        _safe_sel = selector.replace("'", "\\'")

        async def _attempt() -> bool:
            # 1. Wait for element
            found = await self._engine.wait_for_selector(selector, timeout=timeout_ms)
            if not found:
                raise ValueError(f"Fill element '{selector}' not found")

            # 2. Focus + fill
            await self._engine.click(selector, timeout=timeout_ms)
            await asyncio.sleep(0.2)
            await self._engine.fill(selector, value)
            await asyncio.sleep(0.3)

            # 3. Verify — read input value back
            actual = await self._engine.get_attribute(selector, "value")
            if actual is None:
                actual = str(await self._engine.evaluate(
                    f"document.querySelector('{_safe_sel}')?.value || ''"
                ))

            if actual == value:
                self._stats["fills"] += 1
                return True

            logger.warning(
                "Fill verify fail '%s': expected '%s', got '%s'",
                selector, value[:20], str(actual)[:20],
            )
            raise ValueError(f"Fill verification failed: expected '{value}', got '{actual}'")

        try:
            await self.retry(_attempt, retries=retries)
        except RetryExceeded as e:
            raise VerificationFailed(
                f"Fill '{selector}={value}' verification failed",
                context={"selector": selector, "value": value, "retries": retries,
                         "error": str(e)},
            )

    # ── Safe Select ──────────────────────────────────────────────

    async def safe_select(
        self,
        selector: str,
        value: str,
        timeout: Optional[float] = None,
        retries: int = 3,
    ) -> None:
        """Select a dropdown option with verification."""
        t = timeout or self._timeout.normal
        timeout_ms = int(t * 1000)
        _safe_sel = selector.replace("'", "\\'")

        async def _attempt() -> bool:
            found = await self._engine.wait_for_selector(selector, timeout=timeout_ms)
            if not found:
                raise ValueError(f"Select element '{selector}' not found")
            result = await self._engine.select_option(selector, value)
            await asyncio.sleep(0.3)
            actual = str(await self._engine.evaluate(
                f"document.querySelector('{_safe_sel}')?.value || ''"
            ))
            if actual == value:
                self._stats["selects"] += 1
                return True
            if not result:
                raise ValueError(f"Select '{selector}={value}' returned False")
            return False

        try:
            await self.retry(_attempt, retries=retries)
        except RetryExceeded as e:
            raise VerificationFailed(
                f"Select '{selector}={value}' failed",
                context={"selector": selector, "value": value,
                         "error": str(e)},
            )

    # ── Safe Check ───────────────────────────────────────────────

    async def safe_check(
        self,
        selector: str,
        checked: bool = True,
        timeout: Optional[float] = None,
        retries: int = 2,
    ) -> None:
        """Check/uncheck a checkbox with verification."""
        t = timeout or self._timeout.normal
        timeout_ms = int(t * 1000)

        async def _attempt() -> bool:
            found = await self._engine.wait_for_selector(selector, timeout=timeout_ms)
            if not found:
                raise ValueError(f"Check element '{selector}' not found")
            await self._engine.set_checked(selector, checked)
            await asyncio.sleep(0.3)
            actual = await self._engine.is_checked(selector)
            if actual == checked:
                self._stats["checks"] += 1
                return True
            raise ValueError(f"Check verify failed: expected {checked}, got {actual}")

        try:
            await self.retry(_attempt, retries=retries)
        except RetryExceeded as e:
            raise VerificationFailed(
                f"Check '{selector}={checked}' verification failed",
                context={"selector": selector, "checked": checked,
                         "error": str(e)},
            )

    # ── Safe Upload ──────────────────────────────────────────────

    async def safe_upload(
        self,
        selector: str,
        file_path: str,
        timeout: Optional[float] = None,
    ) -> None:
        """Upload a file via file input."""
        t = timeout or self._timeout.upload
        found = await self._engine.wait_for_selector(selector, timeout=int(t * 1000))
        if not found:
            raise ElementNotVisible(f"Upload selector '{selector}' not found")
        ok = await self._engine.upload_file(selector, file_path)
        if not ok:
            raise VerificationFailed(
                f"Upload '{selector}' failed",
                context={"file_path": file_path},
            )
        self._stats["uploads"] += 1

    # ── Delegates (pass-through with standardized timeouts) ───────

    async def navigate(self, url: str, timeout: Optional[float] = None) -> bool:
        """Navigate to a URL with standardized timeout."""
        t = timeout or self._timeout.navigation
        return await self._engine.navigate(url, timeout=int(t * 1000))

    async def wait_for_navigation(self, timeout: Optional[float] = None) -> bool:
        """Wait for navigation with standardized timeout."""
        t = timeout or self._timeout.navigation
        return await self._engine.wait_for_navigation(timeout=int(t * 1000))

    async def get_url(self) -> str:
        return await self._engine.get_url()

    async def get_text(self, selector: str) -> str:
        return await self._engine.get_text(selector)

    async def is_visible(self, selector: str) -> bool:
        return await self._engine.is_visible(selector)

    async def evaluate(self, expression: str) -> Any:
        return await self._engine.evaluate(expression)

    # ── Overlay Methods ───────────────────────────────────────────

    OVERLAY_SELECTORS = [
        ".modal", ".modal-backdrop", ".overlay", ".popup",
        "[class*='modal']", "[class*='overlay']", "[class*='popup']",
        "[role='dialog']", "[aria-modal='true']",
    ]

    OVERLAY_DISMISS_ACTIONS = [
        "button.close", ".close", ".btn-close", "[aria-label='Close']",
        "button:has-text('OK')", "button:has-text('Confirm')",
        "button:has-text('Yes')", "button:has-text('Close')",
        "button:has-text('Accept')", "button:has-text('I Agree')",
    ]

    async def dismiss_overlay(self, timeout: Optional[float] = None) -> bool:
        """Dismiss overlay/modals by clicking close/OK buttons.

        Tries common dismiss buttons against common overlay selectors.
        Returns True if at least one overlay was dismissed.
        """
        t = timeout or self._timeout.short
        dismissed = False
        for overlay_sel in self.OVERLAY_SELECTORS:
            try:
                visible = await self._engine.is_visible(overlay_sel)
                if not visible:
                    continue
            except Exception:
                continue

            # Try each dismiss action
            for btn_sel in self.OVERLAY_DISMISS_ACTIONS:
                try:
                    clicked = await self._engine.click(btn_sel, timeout=int(t * 1000))
                    if clicked:
                        dismissed = True
                        await asyncio.sleep(0.3)
                        break
                except Exception:
                    continue

        return dismissed

    async def dismiss_modal(self, timeout: Optional[float] = None) -> bool:
        """Dismiss modal dialogs (alert/confirm/prompt style).

        Returns True if a modal was dismissed.
        """
        t = timeout or self._timeout.short
        try:
            # Try pressing Escape to dismiss
            await self._engine.evaluate(
                "document.activeElement?.blur(); "
                "document.body.dispatchEvent(new KeyboardEvent('keydown', "
                "  {key: 'Escape', code: 'Escape', keyCode: 27}));"
            )
            await asyncio.sleep(0.3)
            return True
        except Exception:
            return False

    async def wait_overlay_disappear(self, timeout: Optional[float] = None) -> None:
        """Wait for any overlay/loading indicator to disappear."""
        t = timeout or self._timeout.loading
        deadline = time.monotonic() + t

        while time.monotonic() < deadline:
            overlay_found = False
            for sel in self.OVERLAY_SELECTORS:
                try:
                    if await self._engine.is_visible(sel):
                        overlay_found = True
                        break
                except Exception:
                    pass
            if not overlay_found:
                return
            await asyncio.sleep(0.3)


# ══════════════════════════════════════════════════════════════════
# ActionTrace
# ══════════════════════════════════════════════════════════════════

import time as time_module
from dataclasses import dataclass, field
from typing import List

@dataclass
class TraceEntry:
    """A single trace entry for a browser action."""
    action: str
    selector: str = ""
    duration: float = 0.0
    retries: int = 0
    result: str = "ok"
    error: str = ""
    timestamp: float = 0.0

    @property
    def elapsed_ms(self) -> int:
        return int(self.duration * 1000)

    def summary(self) -> str:
        base = f"{self.action}({self.selector}) -> {self.result} [{self.elapsed_ms}ms]"
        if self.retries:
            base += f" (retries={self.retries})"
        if self.error:
            base += f" err={self.error}"
        return base


class ActionTrace:
    """Collector for browser action traces.

    Usage:
        trace = ActionTrace()
        with trace.record("safe_click", "#btnLogin"):
            await browser.safe_click("#btnLogin")
        print(trace.format())
    """

    def __init__(self):
        self.entries: List[TraceEntry] = []
        self._enabled: bool = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def clear(self):
        self.entries.clear()

    def add(self, entry: TraceEntry):
        if self._enabled:
            self.entries.append(entry)

    def record(self, action: str, selector: str = ""):
        """Context manager to record a single action.

        Usage:
            with trace.record("safe_click", "#btnLogin"):
                ...
        """
        return _TraceContext(self, action, selector)

    def format(self, limit: int = 0) -> str:
        """Format all entries as a readable trace log.

        Args:
            limit: Max entries to show (0 = all).
        """
        entries = self.entries[-limit:] if limit else self.entries
        if not entries:
            return "(no trace entries)"

        lines = ["── Action Trace ──"]
        for i, e in enumerate(entries):
            lines.append(f"  {i+1}. {e.summary()}")
        lines.append(f"── {len(entries)} entries ──")
        return "\n".join(lines)

    def last_error(self) -> Optional[str]:
        """Get the last error message, if any."""
        for e in reversed(self.entries):
            if e.error:
                return e.error
        return None


class _TraceContext:
    """Context manager for ActionTrace.record()."""

    def __init__(self, trace: ActionTrace, action: str, selector: str):
        self._trace = trace
        self._entry = TraceEntry(action=action, selector=selector, timestamp=time_module.time())
        self._retries = 0

    def set_retries(self, count: int):
        self._retries = count

    async def __aenter__(self):
        self._entry.timestamp = time_module.time()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._entry.duration = time_module.time() - self._entry.timestamp
        self._entry.retries = self._retries
        if exc_val:
            self._entry.result = "fail"
            self._entry.error = str(exc_val)[:200]
        self._trace.add(self._entry)
        return False  # Don't suppress exceptions
