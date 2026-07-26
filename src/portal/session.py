"""InsureDesk — Session Manager.

Persistent browser session management for portal automation.
Supports: login once, reconnect, detect timeout, auto-recover.
"""

import json
import os
import time
from pathlib import Path
from typing import Optional, Dict
from dataclasses import dataclass


SESSION_DIR = Path.home() / "InsureDesk" / "sessions"


@dataclass
class PortalSession:
    """Stored session state for a portal."""
    adapter_name: str = ""
    logged_in: bool = False
    login_time: float = 0.0
    last_active: float = 0.0
    cookies_file: str = ""
    storage_file: str = ""
    session_id: str = ""


class SessionManager:
    """Manage browser sessions per portal.

    - Saves cookies + localStorage after login
    - Restores on reconnect
    - Detects timeout (>30 min inactivity)
    - Auto-renews session
    """

    SESSION_TIMEOUT = 1800  # 30 minutes

    def __init__(self):
        SESSION_DIR.mkdir(parents=True, exist_ok=True)

    def get_session_path(self, adapter_name: str) -> Path:
        return SESSION_DIR / adapter_name

    def save_cookies(self, adapter_name: str, cookies: list):
        """Save browser cookies to disk."""
        path = self.get_session_path(adapter_name)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "cookies.json", "w") as f:
            json.dump(cookies, f)

    def load_cookies(self, adapter_name: str) -> Optional[list]:
        """Load saved cookies."""
        path = self.get_session_path(adapter_name) / "cookies.json"
        if path.exists():
            with open(path, "r") as f:
                return json.load(f)
        return None

    def save_storage(self, adapter_name: str, storage: dict):
        """Save localStorage/sessionStorage."""
        path = self.get_session_path(adapter_name)
        path.mkdir(parents=True, exist_ok=True)
        with open(path / "storage.json", "w") as f:
            json.dump(storage, f)

    def load_storage(self, adapter_name: str) -> Optional[dict]:
        """Load saved storage state."""
        path = self.get_session_path(adapter_name) / "storage.json"
        if path.exists():
            with open(path, "r") as f:
                data = json.load(f)
            # Restore basic structure
            return data
        return None

    def is_session_valid(self, adapter_name: str) -> bool:
        """Check if a saved session is still valid (not timed out)."""
        path = self.get_session_path(adapter_name) / "cookies.json"
        if not path.exists():
            return False
        mod_time = path.stat().st_mtime
        return (time.time() - mod_time) < self.SESSION_TIMEOUT

    def clear_session(self, adapter_name: str):
        """Clear saved session data."""
        path = self.get_session_path(adapter_name)
        if path.exists():
            import shutil
            shutil.rmtree(path)

    def get_session_info(self, adapter_name: str) -> PortalSession:
        """Get info about a saved session."""
        path = self.get_session_path(adapter_name)
        cookies_path = path / "cookies.json"
        info = PortalSession(adapter_name=adapter_name)
        if cookies_path.exists():
            info.logged_in = True
            info.login_time = cookies_path.stat().st_mtime
            info.last_active = cookies_path.stat().st_mtime
            info.cookies_file = str(cookies_path)
        return info

    def list_sessions(self) -> list:
        """List all stored portal sessions."""
        if not SESSION_DIR.exists():
            return []
        sessions = []
        for d in SESSION_DIR.iterdir():
            if d.is_dir():
                sessions.append({
                    "adapter": d.name,
                    "valid": self.is_session_valid(d.name),
                    "path": str(d),
                })
        return sessions
