"""InsureDesk Drivers — browser automation implementations.

Each subpackage implements BrowserSession + BrowserPage
from src.runtime.browser_session using a specific automation engine.

Available drivers:
- playwright/  — Playwright-based (reference implementation)
- cdp/         — Chrome DevTools Protocol (production target)
"""
