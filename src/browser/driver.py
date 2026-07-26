"""InsureDesk — Browser Driver Interface.

Single abstract interface for all browser automation.

Three implementations:
- PlaywrightDriver — development/testing (headless, CI, selector debugging)
- ChromeCDPDriver  — production (Chrome DevTools Protocol, ships with .exe)
- QtDriver          — future/optional (Qt WebEngine, embedded browser)

FormEngine and PortalAdapter never know which Driver is underneath.
"""

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Callable
from dataclasses import dataclass, field
import asyncio


@dataclass
class PageInfo:
    """Snapshot of current page state."""
    url: str = ""
    title: str = ""
    html: str = ""
    text: str = ""


@dataclass
class Cookie:
    """A browser cookie."""
    name: str = ""
    value: str = ""
    domain: str = ""
    path: str = "/"
    secure: bool = False
    http_only: bool = False
    same_site: str = "Lax"
    expires: int = 0


class BrowserEngine(ABC):
    """Abstract browser engine — all portal automation goes through this.

    Dev:  PlaywrightDriver — full browser, CDP, visible window.
    Prod: ChromeCDPDriver — Chrome DevTools Protocol, connects to existing Chrome.
          QtDriver — Qt WebEngine, embedded browser (optional/future).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Engine name, e.g. 'playwright' or 'webengine'."""
        ...

    @abstractmethod
    async def start(self, headless: bool = False, port: int = 0) -> bool:
        """Start the browser engine."""
        ...

    @abstractmethod
    async def stop(self):
        """Stop the browser engine."""
        ...

    @abstractmethod
    async def navigate(self, url: str, timeout: int = 30000) -> bool:
        """Navigate to a URL. Returns True if successful."""
        ...

    @abstractmethod
    async def get_url(self) -> str:
        """Get the current page URL."""
        ...

    @abstractmethod
    async def get_title(self) -> str:
        """Get the current page title."""
        ...

    @abstractmethod
    async def get_page_info(self) -> PageInfo:
        """Get full page info (url, title, html, text)."""
        ...

    # ── Element Interaction ──

    @abstractmethod
    async def click(self, selector: str, timeout: int = 10000) -> bool:
        """Click an element identified by CSS selector."""
        ...

    @abstractmethod
    async def fill(self, selector: str, value: str, delay_ms: int = 50) -> bool:
        """Type text into an input field."""
        ...

    @abstractmethod
    async def select_option(self, selector: str, value: str) -> bool:
        """Select an option from a dropdown."""
        ...

    @abstractmethod
    async def is_checked(self, selector: str) -> bool:
        """Check if a checkbox/radio is checked."""
        ...

    @abstractmethod
    async def set_checked(self, selector: str, checked: bool) -> bool:
        """Check or uncheck a checkbox/radio."""
        ...

    @abstractmethod
    async def upload_file(self, selector: str, file_path: str) -> bool:
        """Upload a file via file input."""
        ...

    @abstractmethod
    async def get_text(self, selector: str) -> str:
        """Get visible text content of an element."""
        ...

    @abstractmethod
    async def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        """Get an attribute value of an element."""
        ...

    @abstractmethod
    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible."""
        ...

    @abstractmethod
    async def wait_for_selector(self, selector: str, timeout: int = 10000) -> bool:
        """Wait for an element to appear."""
        ...

    @abstractmethod
    async def wait_for_navigation(self, timeout: int = 30000) -> bool:
        """Wait for page navigation to complete."""
        ...

    # ── JavaScript / CDP ──

    @abstractmethod
    async def evaluate(self, script: str) -> Any:
        """Execute JavaScript in the page context and return the result."""
        ...

    @abstractmethod
    async def screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        """Take a screenshot. Returns bytes if no path given."""
        ...

    # ── Session (Cookies) ──

    @abstractmethod
    async def get_cookies(self) -> List[Cookie]:
        """Get all cookies."""
        ...

    @abstractmethod
    async def set_cookies(self, cookies: List[Cookie]):
        """Set cookies."""
        ...

    @abstractmethod
    async def clear_cookies(self):
        """Clear all cookies."""
        ...

    # ── Tabs ──

    @abstractmethod
    async def get_tabs(self) -> int:
        """Get number of open tabs."""
        ...

    @abstractmethod
    async def switch_tab(self, index: int) -> bool:
        """Switch to a specific tab by index."""
        ...

    @abstractmethod
    async def close_tab(self, index: int = -1):
        """Close a tab (-1 = current)."""


# ── Cookie helpers ──

def cookie_to_dict(c: Cookie) -> dict:
    return {
        "name": c.name, "value": c.value, "domain": c.domain,
        "path": c.path, "secure": c.secure, "httpOnly": c.http_only,
        "sameSite": c.same_site, "expires": c.expires,
    }


def dict_to_cookie(d: dict) -> Cookie:
    return Cookie(
        name=d.get("name", ""), value=d.get("value", ""),
        domain=d.get("domain", ""), path=d.get("path", "/"),
        secure=d.get("secure", False), http_only=d.get("httpOnly", False),
        same_site=d.get("sameSite", "Lax"), expires=d.get("expires", 0),
    )
