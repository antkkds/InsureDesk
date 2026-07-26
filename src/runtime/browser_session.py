"""InsureDesk Runtime — Browser Automation Abstraction.

Pure abstraction layer with zero external dependencies.
Playwright, Selenium, or CDP implementations live elsewhere;
this module defines the interfaces they must satisfy.

Layers:
    Adapter → BrowserSession (owns lifecycle/auth)
                   ↓
              BrowserPage (owns click/fill/read/wait)
                   ↓
              PlaywrightSession / CdpSession / MockSession

Usage:
    from src.runtime.browser_session import (
        BrowserSession, BrowserPage, Selector, SessionContext,
        MockBrowserSession, BrowserTimeout, ElementNotFound,
    )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import uuid


# ══════════════════════════════════════════════════════════════════
# Selector — typed locator
# ══════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Selector:
    """A typed browser element selector.

    Usage:
        Selector.id("btnLogin")
        Selector.css("#login-form .submit")
        Selector.xpath("//button[text()='Login']")
        Selector.testid("send-button")
        Selector.text("Submit")
    """
    strategy: str   # css, xpath, id, testid, text
    value: str

    def __post_init__(self):
        VALID_STRATEGIES = {"css", "xpath", "id", "testid", "text"}
        if self.strategy not in VALID_STRATEGIES:
            raise ValueError(f"Invalid selector strategy: {self.strategy}."
                             f" Must be one of {VALID_STRATEGIES}")

    @classmethod
    def css(cls, value: str) -> "Selector":
        return cls(strategy="css", value=value)

    @classmethod
    def xpath(cls, value: str) -> "Selector":
        return cls(strategy="xpath", value=value)

    @classmethod
    def id(cls, value: str) -> "Selector":
        return cls(strategy="id", value=value)

    @classmethod
    def testid(cls, value: str) -> "Selector":
        return cls(strategy="testid", value=value)

    @classmethod
    def text(cls, value: str) -> "Selector":
        return cls(strategy="text", value=value)

    def to_playwright(self) -> str:
        """Convert to Playwright locator string."""
        mapping = {
            "css": lambda v: v,
            "xpath": lambda v: f"xpath={v}",
            "id": lambda v: f"#{v}",
            "testid": lambda v: f'[data-testid="{v}"]',
            "text": lambda v: f'text="{v}"',
        }
        return mapping.get(self.strategy, lambda v: v)(self.value)


# ══════════════════════════════════════════════════════════════════
# BrowserError hierarchy
# ══════════════════════════════════════════════════════════════════

class BrowserError(Exception):
    """Base for all browser automation errors."""
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.context = context or {}


class BrowserTimeout(BrowserError):
    """Operation timed out waiting for something."""


class ElementNotFound(BrowserError):
    """The requested element was not found in the DOM."""


class NavigationFailed(BrowserError):
    """Page navigation failed (wrong URL, network error)."""


class AuthenticationFailed(BrowserError):
    """Login/authentication failed."""


class SessionExpired(BrowserError):
    """Browser session expired or was closed."""


class BrowserClosed(BrowserError):
    """Browser was already closed when attempting an operation."""


# ══════════════════════════════════════════════════════════════════
# SessionContext — execution state
# ══════════════════════════════════════════════════════════════════

@dataclass
class SessionContext:
    """Lightweight execution state shared between runtime and adapters.

    This is NOT browser-automation-specific — it's a runtime concept.
    Adapters can read it when needed, runtime updates it, observability
    traces it without poking into Playwright internals.
    """
    session_id: str = ""
    adapter_name: str = ""
    portal_name: str = ""
    logged_in: bool = False
    current_url: str = ""
    authenticated_user: str = ""
    started_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def create(cls, adapter_name: str = "", portal_name: str = "") -> "SessionContext":
        return cls(
            session_id=uuid.uuid4().hex[:12],
            adapter_name=adapter_name,
            portal_name=portal_name or adapter_name,
            started_at=datetime.utcnow(),
        )


# ══════════════════════════════════════════════════════════════════
# DriverCapabilities — what a browser driver can do
# ══════════════════════════════════════════════════════════════════

@dataclass
class DriverCapabilities:
    """Declared capabilities of a browser driver implementation.

    Lets the runtime query what a driver supports without
    isinstance() checks or importing the implementation.

    Usage:
        if session.capabilities.multiple_tabs:
            page2 = await session.new_page()
    """
    screenshots: bool = True
    javascript: bool = True
    multiple_tabs: bool = True
    download_support: bool = False
    attach_existing: bool = False
    """Whether this driver can attach to an already-running browser."""
    headless: bool = True
    """Whether the driver supports headless mode."""
    name: str = "unknown"
    version: str = "0.0.0"


# ══════════════════════════════════════════════════════════════════
# BrowserFactory — driver registry & creation
# ══════════════════════════════════════════════════════════════════

class BrowserFactory:
    """Registry for browser driver implementations.

    Drivers register themselves on import. The factory creates
    sessions without the runtime knowing which driver is used.

    Usage:
        # Register (called by driver module on import)
        BrowserFactory.register("playwright", PlaywrightSession, caps)

        # Create
        session = BrowserFactory.create("playwright")

        # List available
        for name, caps in BrowserFactory.available():
            print(f"{name}: screenshots={caps.screenshots}")
    """

    _drivers: Dict[str, type] = {}
    _capabilities: Dict[str, DriverCapabilities] = {}

    @classmethod
    def register(
        cls,
        name: str,
        session_cls: type,
        capabilities: Optional[DriverCapabilities] = None,
    ) -> None:
        """Register a browser driver.

        Args:
            name: Driver name (e.g. 'playwright', 'cdp')
            session_cls: Class implementing BrowserSession
            capabilities: Optional driver capabilities
        """
        cls._drivers[name] = session_cls
        if capabilities:
            cls._capabilities[name] = capabilities

    @classmethod
    def create(cls, name: str, **kwargs) -> "BrowserSession":
        """Create a browser session by driver name.

        Args:
            name: Driver name
            **kwargs: Passed to the driver constructor

        Returns:
            BrowserSession instance

        Raises:
            ValueError: If driver not registered
        """
        if name not in cls._drivers:
            available = list(cls._drivers.keys()) or ["none registered"]
            raise ValueError(
                f"Unknown browser driver: '{name}'. "
                f"Available drivers: {available}"
            )
        return cls._drivers[name](**kwargs)

    @classmethod
    def available(cls) -> List[Tuple[str, DriverCapabilities]]:
        """List all registered drivers with their capabilities."""
        return [
            (name, cls._capabilities.get(name, DriverCapabilities(name=name)))
            for name in cls._drivers
        ]

    @classmethod
    def capabilities(cls, name: str) -> Optional[DriverCapabilities]:
        """Get capabilities for a registered driver."""
        return cls._capabilities.get(name)


# ══════════════════════════════════════════════════════════════════
# BrowserPage — individual page/tab
# ══════════════════════════════════════════════════════════════════

class BrowserPage(ABC):
    """A single browser page or tab.

    Owns click/fill/read/wait — browser-level actions only.
    No insurance-specific methods here; those belong in adapters.
    """

    @abstractmethod
    async def goto(self, url: str, timeout: float = 30.0) -> None:
        """Navigate to a URL. Raises NavigationFailed on failure."""
        ...

    @abstractmethod
    async def click(self, selector: Selector, timeout: float = 10.0) -> None:
        """Click an element. Raises ElementNotFound or BrowserTimeout."""
        ...

    @abstractmethod
    async def fill(self, selector: Selector, value: str, timeout: float = 10.0) -> None:
        """Fill a form field. Raises ElementNotFound or BrowserTimeout."""
        ...

    @abstractmethod
    async def text(self, selector: Selector, timeout: float = 10.0) -> str:
        """Get visible text of an element. Raises ElementNotFound."""
        ...

    @abstractmethod
    async def exists(self, selector: Selector, timeout: float = 1.0) -> bool:
        """Check if an element exists (short timeout, never raises)."""
        ...

    @abstractmethod
    async def screenshot(self, full_page: bool = False) -> bytes:
        """Take a screenshot. Returns PNG bytes."""
        ...

    @abstractmethod
    async def wait_for(self, selector: Selector, timeout: float = 10.0) -> None:
        """Wait for element to appear. Raises BrowserTimeout."""
        ...

    @abstractmethod
    async def evaluate(self, expression: str) -> Any:
        """Execute JavaScript in page context. Returns result."""
        ...

    @abstractmethod
    async def url(self) -> str:
        """Get current page URL."""
        ...

    @abstractmethod
    async def title(self) -> str:
        """Get current page title."""
        ...


# ══════════════════════════════════════════════════════════════════
# BrowserSession — browser lifecycle & auth
# ══════════════════════════════════════════════════════════════════

@dataclass
class Credentials:
    """Credentials for portal login."""
    username: str = ""
    password: str = ""
    url: str = ""
    additional: Dict[str, str] = field(default_factory=dict)


class BrowserSession(ABC):
    """A browser session owned by the runtime.

    Owns:
    - Authentication / cookies
    - Browser lifecycle (start/close)
    - Context isolation

    Adapters interact with this, not with Playwright directly.
    """

    def __init__(self):
        self._context: SessionContext = SessionContext.create()

    @property
    def context(self) -> SessionContext:
        """Get the session context (read-only view for adapters)."""
        return self._context

    @abstractmethod
    async def start(self) -> None:
        """Launch the browser. Must be called before any other method."""
        ...

    @abstractmethod
    async def login(self, credentials: Credentials) -> bool:
        """Log in to a portal.

        Returns True if login succeeded.
        Raises AuthenticationFailed on invalid credentials.
        Raises BrowserTimeout if login page doesn't load.
        """
        ...

    @abstractmethod
    async def new_page(self) -> BrowserPage:
        """Open a new tab/page. Returns a BrowserPage instance."""
        ...

    @abstractmethod
    async def close(self) -> None:
        """Close the browser and release resources."""
        ...


# ══════════════════════════════════════════════════════════════════
# MockBrowserSession — in-memory, no Playwright
# ══════════════════════════════════════════════════════════════════

class MockPage(BrowserPage):
    """In-memory BrowserPage for testing. Never imports Playwright."""

    def __init__(self):
        self.current_url = "about:blank"
        self.page_title = ""
        self.elements: Dict[str, str] = {}       # selector.value → text content
        self.inputs: Dict[str, str] = {}          # selector.value → filled value
        self.clicked: List[str] = []              # selector values clicked
        self.screenshots: List[bytes] = []
        self.errors: Dict[str, Exception] = {}    # selector.value → error to raise
        self._closed = False

    async def goto(self, url: str, timeout: float = 30.0) -> None:
        if self._closed:
            raise BrowserClosed("Page is closed")
        self.current_url = url
        self.page_title = f"Mock: {url}"

    async def click(self, selector: Selector, timeout: float = 10.0) -> None:
        if self._closed:
            raise BrowserClosed("Page is closed")
        if selector.value in self.errors:
            raise self.errors[selector.value]
        self.clicked.append(selector.value)
        # Auto-navigate based on click (simulate form submission)
        if selector.value == "btnLogin":
            self.current_url = "/dashboard"
            self.page_title = "Dashboard"

    async def fill(self, selector: Selector, value: str, timeout: float = 10.0) -> None:
        if self._closed:
            raise BrowserClosed("Page is closed")
        if selector.value in self.errors:
            raise self.errors[selector.value]
        self.inputs[selector.value] = value

    async def text(self, selector: Selector, timeout: float = 10.0) -> str:
        if self._closed:
            raise BrowserClosed("Page is closed")
        if selector.value in self.errors:
            raise self.errors[selector.value]
        return self.elements.get(selector.value, "")

    async def exists(self, selector: Selector, timeout: float = 1.0) -> bool:
        if self._closed:
            return False
        return selector.value in self.elements or selector.value in self.inputs

    async def screenshot(self, full_page: bool = False) -> bytes:
        if self._closed:
            raise BrowserClosed("Page is closed")
        data = b"mock_screenshot_bytes"
        self.screenshots.append(data)
        return data

    async def wait_for(self, selector: Selector, timeout: float = 10.0) -> None:
        if self._closed:
            raise BrowserClosed("Page is closed")
        if selector.value in self.errors:
            raise self.errors[selector.value]
        if not await self.exists(selector):
            raise BrowserTimeout(f"Element {selector.value} not found within {timeout}s")

    async def evaluate(self, expression: str) -> Any:
        if self._closed:
            raise BrowserClosed("Page is closed")
        if expression == "document.title":
            return self.page_title
        if expression.startswith("window.location"):
            return self.current_url
        return None

    async def url(self) -> str:
        return self.current_url

    async def title(self) -> str:
        return self.page_title


class MockBrowserSession(BrowserSession):
    """In-memory BrowserSession for testing. Never imports Playwright.

    Usage:
        session = MockBrowserSession()
        await session.start()
        page = await session.new_page()
        await page.goto("https://portal.example.com")
        await page.fill(Selector.id("username"), "user")
        assert page.inputs["username"] == "user"
        await session.close()
    """

    def __init__(self):
        super().__init__()
        self.pages: List[MockPage] = []
        self._started = False
        self._closed = False
        self.login_called = False
        self.login_success = True
        self.last_credentials: Optional[Credentials] = None

    async def start(self) -> None:
        self._started = True
        self._context.started_at = datetime.utcnow()

    async def login(self, credentials: Credentials) -> bool:
        self.login_called = True
        self.last_credentials = credentials
        if not self._started:
            raise BrowserClosed("Session not started")

        if not credentials.username or not credentials.password:
            raise AuthenticationFailed("Missing credentials")

        self._context.logged_in = self.login_success
        self._context.authenticated_user = credentials.username
        self._context.current_url = credentials.url or "https://portal.example.com/dashboard"
        return self.login_success

    async def new_page(self) -> MockPage:
        if not self._started:
            raise BrowserClosed("Session not started")
        page = MockPage()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self._closed = True
        self._started = False
        # Mark all pages as closed
        for page in self.pages:
            page._closed = True
        self.pages.clear()

    @property
    def is_started(self) -> bool:
        return self._started

    @property
    def is_closed(self) -> bool:
        return self._closed
