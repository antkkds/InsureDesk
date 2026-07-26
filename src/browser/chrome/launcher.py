"""Chrome launcher — find, start, stop Chrome with CDP enabled.

No user needs to remember --remote-debugging-port.
InsureDesk handles everything automatically.
"""

import asyncio
import json
import os
import platform
import subprocess
import time
from typing import Optional
import urllib.request


class ChromeLauncher:
    """Find Chrome on the system and launch it with CDP enabled."""

    DEFAULT_PORT = 9222

    @staticmethod
    def find_chrome() -> Optional[str]:
        """Locate the Chrome/Chromium executable."""
        system = platform.system()

        if system == "Windows":
            paths = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles%\Chromium\Application\chrome.exe"),
            ]
            for p in paths:
                if os.path.exists(p):
                    return p
            # Try where command
            try:
                result = subprocess.run(["where", "chrome"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip().split("\n")[0]
            except Exception:
                pass

        elif system == "Linux":
            paths = [
                "/usr/bin/google-chrome",
                "/usr/bin/google-chrome-stable",
                "/usr/bin/chromium",
                "/usr/bin/chromium-browser",
                "/snap/bin/chromium",
            ]
            for p in paths:
                if os.path.exists(p):
                    return p
            try:
                result = subprocess.run(["which", "google-chrome", "chromium", "chromium-browser"],
                                        capture_output=True, text=True, timeout=5)
                if result.stdout.strip():
                    return result.stdout.strip().split("\n")[0]
            except Exception:
                pass

        elif system == "Darwin":
            paths = [
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
            ]
            for p in paths:
                if os.path.exists(p):
                    return p

        return None

    @staticmethod
    def is_chrome_running(port: int = DEFAULT_PORT) -> bool:
        """Check if Chrome with CDP is already running on the given port."""
        try:
            req = urllib.request.Request(f"http://localhost:{port}/json/version")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                return "Browser" in data
        except Exception:
            return False

    @staticmethod
    def get_browser_ws_url(port: int = DEFAULT_PORT) -> Optional[str]:
        """Get the browser-level WebSocket debugger URL."""
        try:
            req = urllib.request.Request(f"http://localhost:{port}/json/version")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                return data.get("webSocketDebuggerUrl")
        except Exception:
            return None

    @staticmethod
    def get_page_targets(port: int = DEFAULT_PORT) -> list:
        """Get all page targets (tabs) from Chrome."""
        try:
            req = urllib.request.Request(f"http://localhost:{port}/json")
            with urllib.request.urlopen(req, timeout=3) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            return []

    @staticmethod
    def launch_chrome(
        chrome_path: str,
        port: int = DEFAULT_PORT,
        profile_dir: Optional[str] = None,
        headless: bool = False,
    ) -> subprocess.Popen:
        """Launch Chrome with remote debugging enabled.

        Args:
            chrome_path: Path to Chrome executable.
            port: CDP port (default: 9222).
            profile_dir: Custom profile directory. If None, uses a temp dir.
            headless: Run in headless mode.

        Returns:
            Popen object for the Chrome process.
        """
        args = [
            chrome_path,
            f"--remote-debugging-port={port}",
            "--no-first-run",
            "--no-default-browser-check",
        ]

        if profile_dir:
            args.append(f"--user-data-dir={profile_dir}")

        if headless:
            args.append("--headless=new")

        # Don't open any tab
        args.append("about:blank")

        return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @staticmethod
    async def wait_for_cdp(port: int = DEFAULT_PORT, timeout: float = 30.0) -> bool:
        """Wait until Chrome's CDP endpoint is ready."""
        start = time.time()
        while time.time() - start < timeout:
            if ChromeLauncher.is_chrome_running(port):
                return True
            await asyncio.sleep(0.5)
        return False

    @staticmethod
    def kill_chrome(port: int = DEFAULT_PORT):
        """Kill Chrome instances on the given port.

        On Windows, this finds and kills the process.
        On Linux/Mac, uses pkill.
        """
        system = platform.system()
        try:
            if system == "Windows":
                # Find Chrome process by port — rough approach
                result = subprocess.run(
                    ["netstat", "-ano"], capture_output=True, text=True, timeout=10
                )
                for line in result.stdout.split("\n"):
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        if parts:
                            pid = parts[-1]
                            subprocess.run(["taskkill", "/F", "/PID", pid],
                                         capture_output=True, timeout=5)
                            break
            else:
                subprocess.run(["pkill", "-f", f"--remote-debugging-port={port}"],
                             capture_output=True, timeout=5)
        except Exception:
            pass
