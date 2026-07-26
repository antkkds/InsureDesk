"""Tab/Target management for Chrome CDP.

Discover, filter, and attach to Chrome tabs.
"""

import json
from typing import Optional, List
import urllib.request


class TabInfo:
    """Information about a Chrome tab/page target."""

    def __init__(self, target: dict):
        self.id: str = target.get("id", "")
        self.title: str = target.get("title", "")
        self.url: str = target.get("url", "")
        self.ws_url: str = target.get("webSocketDebuggerUrl", "")
        self.type: str = target.get("type", "")  # "page", "iframe", etc.

    def __repr__(self):
        return f"TabInfo(id={self.id[:12]}..., title={self.title[:30]})"


def list_tabs(port: int = 9222) -> List[TabInfo]:
    """List all page-type targets (tabs) from Chrome CDP.

    Args:
        port: CDP port.

    Returns:
        List of TabInfo for page-type targets.
    """
    try:
        req = urllib.request.Request(f"http://localhost:{port}/json")
        with urllib.request.urlopen(req, timeout=3) as resp:
            targets = json.loads(resp.read().decode())
        return [TabInfo(t) for t in targets if t.get("type") == "page"]
    except Exception:
        return []


def find_tab_by_domain(port: int, domain: str) -> Optional[TabInfo]:
    """Find a tab whose URL matches the given domain.

    Args:
        port: CDP port.
        domain: Domain pattern (e.g. "greateasternlife.com").

    Returns:
        TabInfo if found, None otherwise.
    """
    for tab in list_tabs(port):
        if domain in tab.url:
            return tab
    return None


def find_tab_by_url_pattern(port: int, pattern: str) -> Optional[TabInfo]:
    """Find a tab whose URL contains the given pattern.

    Args:
        port: CDP port.
        pattern: URL substring to match.

    Returns:
        TabInfo if found, None otherwise.
    """
    for tab in list_tabs(port):
        if pattern in tab.url:
            return tab
    return None


def create_tab(port: int, url: str = "about:blank") -> Optional[TabInfo]:
    """Open a new tab in Chrome via CDP.

    Args:
        port: CDP port.
        url: URL to open in the new tab.

    Returns:
        TabInfo for the new tab if successful.
    """
    try:
        import urllib.parse
        encoded_url = urllib.parse.quote(url, safe="")
        req = urllib.request.Request(
            f"http://localhost:{port}/json/new?{encoded_url}"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            target = json.loads(resp.read().decode())
        return TabInfo(target)
    except Exception:
        return None


def close_tab(port: int, tab_id: str) -> bool:
    """Close a tab by its target ID.

    Args:
        port: CDP port.
        tab_id: Target ID of the tab to close.

    Returns:
        True if successful.
    """
    try:
        req = urllib.request.Request(
            f"http://localhost:{port}/json/close/{tab_id}"
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            return b"ok" in resp.read().lower()
    except Exception:
        return False


def activate_tab(port: int, tab_id: str) -> bool:
    """Bring a tab to the foreground.

    Args:
        port: CDP port.
        tab_id: Target ID of the tab to activate.

    Returns:
        True if successful.
    """
    try:
        req = urllib.request.Request(
            f"http://localhost:{port}/json/activate/{tab_id}"
        )
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False
