#!/usr/bin/env python3
"""InsureDesk Bridge Server — Headless startup.

Starts the local Bridge Server for UIP-AI to call insurance tools.

Usage:
    python run_bridge.py                    # Default port 8199
    python run_bridge.py --port 9199        # Custom port
    python run_bridge.py --daemon           # Background mode
    python run_bridge.py --help             # Full options

After build:
    InsureDeskBridge.exe                    # Windows
    ./InsureDeskBridge                      # Linux/Mac
"""

from __future__ import annotations

import sys
import os
import argparse
import signal
import time
import json
from pathlib import Path

# Ensure project root is on path
# Support both development and PyInstaller bundle modes
if getattr(sys, 'frozen', False):
    # Running in PyInstaller bundle
    PROJECT_ROOT = Path(sys._MEIPASS)
else:
    # Running from source
    PROJECT_ROOT = Path(__file__).resolve().parent

sys.path.insert(0, str(PROJECT_ROOT))


def main():
    parser = argparse.ArgumentParser(
        description="InsureDesk Bridge Server — Local execution bridge for UIP-AI",
    )
    parser.add_argument(
        "--port", type=int, default=8199,
        help="Port to listen on (default: 8199)",
    )
    parser.add_argument(
        "--host", type=str, default="127.0.0.1",
        help="Host to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--daemon", action="store_true",
        help="Run in background (daemon mode)",
    )
    parser.add_argument(
        "--init-db", action="store_true",
        help="Initialize database on startup",
    )
    parser.add_argument(
        "--health", action="store_true",
        help="Check health and exit",
    )
    parser.add_argument(
        "--version", action="store_true",
        help="Show version and exit",
    )

    args = parser.parse_args()

    if args.version:
        print("InsureDesk Bridge v1.0.0")
        return

    # Initialize database if requested
    if args.init_db:
        try:
            from src.database.db_manager import init_db, get_engine, seed_companies
            engine = init_db()
            from src.database.db_manager import get_session
            session = get_session(engine)
            seed_companies(session)
            session.close()
            print(f"✓ Database initialized at {Path.home() / 'InsureDesk' / 'insuredesk.db'}")
        except Exception as e:
            print(f"✗ Database init failed: {e}")

    # Start bridge server
    from src.bridge.server import BridgeServer

    server = BridgeServer(port=args.port, host=args.host)

    # Health check mode
    if args.health:
        # Quick start then check
        server.start()
        try:
            import urllib.request
            resp = urllib.request.urlopen(
                f"http://{args.host}:{server.port}/api/v1/health",
                timeout=5,
            )
            data = json.loads(resp.read().decode())
            print(json.dumps(data, indent=2))
        except Exception as e:
            print(f"✗ Health check failed: {e}")
            sys.exit(1)
        finally:
            server.stop()
        return

    # Normal mode
    server.start()

    # Handle graceful shutdown
    shutdown_requested = False

    def handle_signal(sig, frame):
        nonlocal shutdown_requested
        if shutdown_requested:
            print("\nForce exit.")
            sys.exit(1)
        shutdown_requested = True
        print(f"\nShutting down bridge server...")
        server.stop()
        print("Bridge server stopped.")
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    print(f"\n{'='*50}")
    print(f"  InsureDesk Bridge Server")
    print(f"  URL:      http://{args.host}:{server.port}")
    print(f"  Health:   http://{args.host}:{server.port}/api/v1/health")
    print(f"  Tools:    http://{args.host}:{server.port}/api/v1/tools")
    print(f"  Execute:  POST http://{args.host}:{server.port}/api/v1/execute")
    print(f"{'='*50}")
    print(f"  Press Ctrl+C to stop")
    print()

    # Keep main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        handle_signal(None, None)


if __name__ == "__main__":
    main()
