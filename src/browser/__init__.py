"""InsureDesk — Browser Driver Factory.

Auto-selects the best available browser driver:
1. ChromeCDPDriver (production) — Chrome DevTools Protocol
2. PlaywrightDriver (development) — Playwright (pip install playwright)
3. QtDriver (future/optional) — PySide6 QtWebEngine

Raises clear error if none are available.
"""

from src.browser.driver import BrowserEngine


def create_browser_engine(prefer: str = "auto") -> BrowserEngine:
    """Create the best available browser engine.

    Args:
        prefer: 'auto' (default), 'chrome', 'playwright', or 'qt'

    Returns a started BrowserEngine instance.
    Raises RuntimeError if no engine is available.
    """
    if prefer == "chrome":
        return _try_chrome() or _try_playwright() or _try_qt() or _raise_no_engine()
    elif prefer == "playwright":
        return _try_playwright() or _try_chrome() or _try_qt() or _raise_no_engine()
    elif prefer == "qt":
        return _try_qt() or _try_chrome() or _try_playwright() or _raise_no_engine()

    # auto: try chrome first (production), fallback to playwright (dev), then qt
    return _try_chrome() or _try_playwright() or _try_qt() or _raise_no_engine()


def _try_chrome() -> BrowserEngine:
    try:
        from src.browser.chrome.cdp_driver import ChromeCDPDriver
        import websockets  # noqa — verify dependency
        return ChromeCDPDriver()
    except ImportError:
        return None


def _try_playwright() -> BrowserEngine:
    try:
        from src.browser.playwright.driver import PlaywrightDriver
        import playwright  # noqa — verify dependency
        return PlaywrightDriver()
    except ImportError:
        return None


def _try_qt() -> BrowserEngine:
    try:
        from src.browser.qt_driver import QtDriver
        # Just check import works — don't start yet
        return QtDriver()
    except ImportError:
        return None


def _raise_no_engine():
    raise RuntimeError(
        "No browser engine available.\n\n"
        "For PRODUCTION: No setup needed — ChromeCDPDriver uses your existing Chrome.\n"
        "For DEVELOPMENT: pip install playwright && python -m playwright install chromium\n"
    )
