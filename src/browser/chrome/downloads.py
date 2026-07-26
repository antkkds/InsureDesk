"""Download management for Chrome CDP.

Handles file downloads triggered by portal automation.
Uses CDP's Browser.setDownloadBehavior to control save locations.
"""

import json
import os
from typing import Optional


def setup_download_behavior(cdp_ws_url: str, download_dir: str):
    """Configure Chrome to auto-download files to a specific directory.

    This must be called on the page-level CDP connection before
    any download-triggering actions.

    Args:
        cdp_ws_url: Page-level WebSocket debugger URL.
        download_dir: Absolute path where files should be saved.
    """
    # This is done via CDP command on the page connection
    # Implementation is in CdpConnection.send_command
    pass


def get_download_dir(base_dir: str = None) -> str:
    """Get the download directory for InsureDesk.

    Creates the directory if it doesn't exist.

    Args:
        base_dir: Base directory. Defaults to user's Downloads/InsureDesk.

    Returns:
        Absolute path to the download directory.
    """
    if base_dir is None:
        import platform
        home = os.path.expanduser("~")
        if platform.system() == "Windows":
            base_dir = os.path.join(os.environ.get("USERPROFILE", home), "Downloads")
        else:
            base_dir = os.path.join(home, "Downloads")
        base_dir = os.path.join(base_dir, "InsureDesk")

    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def find_latest_download(download_dir: str, pattern: str = None) -> Optional[str]:
    """Find the most recently downloaded file in the directory.

    Args:
        download_dir: Directory to search.
        pattern: Optional filename substring filter.

    Returns:
        Absolute path to the latest file, or None.
    """
    if not os.path.isdir(download_dir):
        return None

    files = []
    for f in os.listdir(download_dir):
        fpath = os.path.join(download_dir, f)
        if os.path.isfile(fpath):
            if pattern and pattern.lower() not in f.lower():
                continue
            # Skip temporary Chrome download files (.crdownload)
            if f.endswith(".crdownload"):
                continue
            files.append((os.path.getmtime(fpath), fpath))

    if not files:
        return None

    files.sort(key=lambda x: x[0], reverse=True)
    return files[0][1]
