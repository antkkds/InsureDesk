"""InsureDesk Drivers — CDP (Chrome DevTools Protocol) browser automation.

Production-quality browser driver that connects to an existing Chrome instance.
No Playwright dependency — uses websockets + CDP commands directly.

Usage:
    from src.drivers.cdp import CdpSession

    session = CdpSession(port=9222)
    await session.start()
    page = await session.new_page()
    ...
    await session.close()

Or via factory:
    from src.runtime.browser_session import BrowserFactory
    session = BrowserFactory.create("cdp", port=9222)
"""

from src.drivers.cdp.session import CdpSession
from src.drivers.cdp.page import CdpPage

__all__ = ["CdpSession", "CdpPage"]
