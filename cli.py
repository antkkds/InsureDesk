#!/usr/bin/env python3
"""InsureDesk — CLI Entry Point.

Usage:
    insuredesk                        # Launch desktop GUI
    insuredesk --install-browser      # Install Playwright browser
    insuredesk --version              # Show version
    insuredesk --help                 # Show this help
"""
from __future__ import annotations

import argparse
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build.version import VERSION


def install_browser() -> None:
    """Install Playwright Chromium for bundled use."""
    print("Installing Playwright Chromium...")
    import subprocess
    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print("✅ Chromium installed")
    else:
        print(f"❌ Failed: {result.stderr}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="InsureDesk — Insurance Agent Desktop",
    )
    parser.add_argument(
        "--install-browser", action="store_true",
        help="Install Playwright Chromium browser",
    )
    parser.add_argument(
        "--version", action="store_true",
        help="Show version",
    )
    args = parser.parse_args()

    if args.version:
        print(f"InsureDesk v{VERSION}")
        return

    if args.install_browser:
        install_browser()
        return

    # Default: launch desktop GUI
    from src.desktop.app import InsureDeskWindow
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("InsureDesk")
    app.setOrganizationName("UIP-AI")

    window = InsureDeskWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
