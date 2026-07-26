"""InsureDesk Drivers — Playwright browser automation.

This module requires `playwright` to be installed.
It registers itself with BrowserFactory on import.

Usage:
    from src.drivers.playwright import PlaywrightSession

    session = PlaywrightSession()
    await session.start()
    page = await session.new_page()
    await page.goto("https://example.com")
    ...
    await session.close()

Or via factory:
    from src.runtime.browser_session import BrowserFactory
    session = BrowserFactory.create("playwright")
"""

from src.drivers.playwright.session import PlaywrightSession
from src.drivers.playwright.page import PlaywrightPage

__all__ = ["PlaywrightSession", "PlaywrightPage"]
