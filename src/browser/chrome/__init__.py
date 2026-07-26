"""InsureDesk — Chrome CDP Subsystem.

Production browser driver using Chrome DevTools Protocol.
Connects to existing Chrome or auto-launches one.
No Playwright, no QtWebEngine required.
"""

from src.browser.chrome.manager import ChromeManager
from src.browser.chrome.cdp_driver import ChromeCDPDriver
