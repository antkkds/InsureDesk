"""InsureDesk — PortalDriver Protocol.

Minimal contract for portal browser drivers, shaped around the existing
FormEngine surface. Deliberately does NOT include autocomplete/postback
helpers — those stay portal-specific until Motor proves they are needed.

The protocol is the thin seam between FormSpec (declarative) and the
browser layer (imperative). Any driver that satisfies it can execute any
FormSpec; any FormSpec can run on any driver.

Current implementations:
    - src.portal.form_engine.FormEngine  (primary, Playwright/CDP backed)
    - tests.mock_browser.MockBrowser     (test double)

Usage:
    from src.portal.protocol import PortalDriver, ActionResult

    async def run(driver: PortalDriver, spec: MotorPrivateCarSpec):
        for section in spec.sections:
            for field in section.fields:
                result = await driver.fill(field.selector, value)
                if not result.success:
                    raise FormFillError(result.error)
"""
from __future__ import annotations

from typing import Protocol, Optional, runtime_checkable

from src.portal.action_result import ActionResult


@runtime_checkable
class PortalDriver(Protocol):
    """Minimal browser driver contract for executing FormSpecs.

    Method names follow the existing FormEngine surface (fill_text,
    select_option, ...) so the primary driver satisfies the protocol
    without wrappers. All interactions return ActionResult so every
    action is observable: success/failure, timing, attempts, trace.

    Implementations:
        - src.portal.form_engine.FormEngine  (primary, Playwright/CDP)
        - tests.mock_browser.MockBrowser     (test double)
    """

    async def navigate(self, url: str) -> ActionResult:
        """Navigate to a URL. Must wait for the main frame to settle."""
        ...

    async def fill_text(self, selector: str, value: str) -> ActionResult:
        """Type a value into a text-like input (text, textarea, date)."""
        ...

    async def select_option(self, selector: str, value: str) -> ActionResult:
        """Choose an option from a <select> dropdown by value/label."""
        ...

    async def click(self, selector: str) -> ActionResult:
        """Click an element (button, radio, checkbox, mat-option, link)."""
        ...

    async def get_text(self, selector: str) -> str:
        """Read current text/value of an element (empty string if missing)."""
        ...

    async def wait_for_selector(self, selector: str, timeout_ms: int = 10000) -> ActionResult:
        """Wait for an element to be present/visible."""
        ...

    async def upload_file(self, selector: str, file_path: str) -> ActionResult:
        """Attach a file to an upload input."""
        ...

    async def screenshot(self, path: Optional[str] = None) -> Optional[bytes]:
        """Capture a screenshot for evidence. Returns image bytes."""
        ...

    async def evaluate(self, script: str) -> object:
        """Run arbitrary JS in page context (used sparingly)."""
        ...
