#!/usr/bin/env python3
"""Build InsureDesk Bridge executable.

Usage:
    python scripts/build_exe.py                    # Build bridge server
    python scripts/build_exe.py --gui              # Include GUI (requires PySide6)
    python scripts/build_exe.py --clean            # Clean build
    python scripts/build_exe.py --test             # Build and test
"""

from __future__ import annotations

import sys
import os
import subprocess
import shutil
import argparse
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_DIR / "dist"
BUILD_DIR = PROJECT_DIR / "build"
SPEC_FILE = PROJECT_DIR / "insuredesk.spec"


def main():
    parser = argparse.ArgumentParser(
        description="Build InsureDesk Bridge executable",
    )
    parser.add_argument("--clean", action="store_true",
                        help="Clean build artifacts before building")
    parser.add_argument("--test", action="store_true",
                        help="Build then run health check")
    parser.add_argument("--gui", action="store_true",
                        help="Include GUI (requires PySide6)")
    args = parser.parse_args()

    # Check PyInstaller
    if not shutil.which("pyinstaller"):
        print("✗ PyInstaller not found. Install with: pip install pyinstaller")
        sys.exit(1)

    # Clean
    if args.clean:
        print("Cleaning build artifacts...")
        for d in [DIST_DIR, BUILD_DIR]:
            if d.exists():
                shutil.rmtree(d)
                print(f"  Removed {d}")

        # Also clean PyInstaller cache
        cache_dir = Path.home() / ".cache" / "pyinstaller"
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
            print(f"  Removed {cache_dir}")

    # Ensure spec file exists
    if not SPEC_FILE.exists():
        print(f"✗ Spec file not found: {SPEC_FILE}")
        sys.exit(1)

    # Build
    print(f"\nBuilding InsureDesk Bridge...")
    print(f"  Project: {PROJECT_DIR}")
    print(f"  Spec:    {SPEC_FILE}")
    print(f"  Output:  {DIST_DIR}")
    print()

    cmd = [
        "pyinstaller",
        str(SPEC_FILE),
        "--noconfirm",
    ]
    if args.clean:
        cmd.append("--clean")

    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        print(f"\n✗ Build failed (exit code {result.returncode})")
        sys.exit(1)

    # Check output
    if sys.platform == "win32":
        exe_path = DIST_DIR / "InsureDeskBridge" / "InsureDeskBridge.exe"
    else:
        exe_path = DIST_DIR / "InsureDeskBridge"

    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print(f"\n✓ Build complete!")
        print(f"  Executable: {exe_path}")
        print(f"  Size:       {size_mb:.1f} MB")
    else:
        print(f"\n⚠ Build may have failed — executable not found at {exe_path}")
        # Check for alternative output
        for f in DIST_DIR.rglob("*"):
            if f.is_file() and "InsureDesk" in f.name:
                print(f"  Found: {f}")

    # Test
    if args.test:
        print("\nRunning health check...")
        test_result = subprocess.run(
            [str(exe_path), "--health"],
            capture_output=True, text=True, timeout=10,
        )
        if test_result.returncode == 0 and test_result.stdout:
            print(test_result.stdout)
            print("✓ Health check passed!")
        else:
            print(f"✗ Health check failed")
            if test_result.stderr:
                print(f"  stderr: {test_result.stderr[:500]}")


if __name__ == "__main__":
    main()
