"""ChromeManager — full lifecycle management for Chrome CDP.

Orchestrates:
- Finding or launching Chrome
- Heartbeat + auto-reconnect
- Tab discovery and attachment
- Clean shutdown
"""

import asyncio
import os
import platform
import socket
import tempfile
from typing import Optional, Callable

from src.browser.chrome.launcher import ChromeLauncher
from src.browser.chrome.tabs import list_tabs, find_tab_by_domain, create_tab, TabInfo


class ChromeManager:
    """Manages a Chrome instance for portal automation.

    Usage:
        manager = ChromeManager()
        await manager.start()
        tab = await manager.ensure_tab("greateasternlife.com")
        driver = ChromeCDPDriver(connection=tab.connection)
    """

    def __init__(self, port: int = 9222, profile_dir: str = None):
        self.port = port
        self.profile_dir = profile_dir or self._default_profile_dir()
        self._chrome_process = None
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._on_disconnect: Optional[Callable] = None
        self._connections: list = []

    @staticmethod
    def _find_free_port() -> int:
        """Find a free TCP port on localhost."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    @staticmethod
    def _default_profile_dir() -> str:
        """Get the default InsureDesk Chrome profile directory."""
        system = platform.system()
        if system == "Windows":
            base = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        else:
            base = os.path.join(os.path.expanduser("~"), ".local", "share")
        return os.path.join(base, "InsureDesk", "ChromeProfile")

    async def start(self):
        """Ensure Chrome is running with CDP enabled.

        If Chrome is already running on the CDP port, connects to it.
        Otherwise, launches a new Chrome instance.
        """
        if self._running:
            return

        # Auto-select free port if none specified
        if self.port == 0:
            self.port = self._find_free_port()

        # Check if Chrome is already running with CDP
        if ChromeLauncher.is_chrome_running(self.port):
            self._running = True
            self._start_heartbeat()
            return

        # Find Chrome executable
        chrome_path = ChromeLauncher.find_chrome()
        if not chrome_path:
            raise RuntimeError(
                "Chrome not found on this system. "
                "Please install Google Chrome or Chromium."
            )

        # Ensure profile directory exists
        os.makedirs(self.profile_dir, exist_ok=True)

        # Launch Chrome
        self._chrome_process = ChromeLauncher.launch_chrome(
            chrome_path=chrome_path,
            port=self.port,
            profile_dir=self.profile_dir,
        )

        # Wait for CDP to be ready
        ready = await ChromeLauncher.wait_for_cdp(self.port, timeout=30.0)
        if not ready:
            raise RuntimeError("Chrome started but CDP not responding")

        self._running = True
        self._start_heartbeat()
        return True

    def _start_heartbeat(self):
        """Start background heartbeat to detect disconnection."""
        if self._heartbeat_task and not self._heartbeat_task.done():
            return
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

    async def _heartbeat_loop(self):
        """Periodically check if Chrome is still alive."""
        while self._running:
            await asyncio.sleep(5)
            try:
                alive = ChromeLauncher.is_chrome_running(self.port)
                if not alive:
                    self._running = False
                    if self._on_disconnect:
                        await self._on_disconnect()
                    # Auto-reconnect
                    await self.start()
                    self._running = True
            except Exception:
                pass

    async def ensure_tab(self, domain: str, url: str = None) -> Optional[TabInfo]:
        """Find a tab for the given domain, or create one.

        Args:
            domain: Domain to match (e.g. "greateasternlife.com").
            url: URL to navigate to if creating a new tab.

        Returns:
            TabInfo for the matched/created tab.
        """
        # Try to find existing tab
        tab = find_tab_by_domain(self.port, domain)
        if tab:
            return tab

        # Create new tab
        open_url = url or f"https://{domain}"
        return create_tab(self.port, open_url)

    async def stop(self):
        """Stop Chrome manager and clean up."""
        self._running = False

        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except Exception:
                pass
            self._heartbeat_task = None

        # Close all CDP connections
        for conn in self._connections:
            try:
                await conn.close()
            except Exception:
                pass
        self._connections.clear()

        if self._chrome_process:
            try:
                self._chrome_process.terminate()
                await asyncio.sleep(1)
                if self._chrome_process.poll() is None:
                    self._chrome_process.kill()
                self._chrome_process.wait(timeout=5)
            except Exception:
                pass
            self._chrome_process = None

    def on_disconnect(self, callback: Callable):
        """Register callback for Chrome disconnection events."""
        self._on_disconnect = callback

    @property
    def is_running(self) -> bool:
        return self._running
