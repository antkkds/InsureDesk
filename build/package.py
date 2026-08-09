"""InsureDesk — Build Automation Script.

Produces:
    dist/InsureDesk/          ← One-folder portable build
    dist/InsureDesk-Setup.exe ← Windows installer (if Inno Setup available)

Usage:
    python build/package.py              # Full build
    python build/package.py --quick      # PyInstaller only, skip installer
    python build/package.py --installer  # PyInstaller + Inno Setup
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parent

DIST = ROOT / "dist"
BUILD_DIR = ROOT / "build"
APP_DIR = DIST / "InsureDesk"
VENV = ROOT / "venv"


def get_version() -> str:
    vf = BUILD_DIR / "version.txt"
    return vf.read_text().strip() if vf.exists() else "1.0.0"


def clean() -> None:
    """Remove previous build artifacts."""
    for d in [ROOT / "build" / "pyinstaller", DIST]:
        if d.exists():
            shutil.rmtree(d)
    print("🧹 Cleaned build artifacts")


def install_deps() -> None:
    """Ensure all build dependencies are installed."""
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"],
        check=True,
    )
    print("📦 Build dependencies ready")


def run_pyinstaller() -> None:
    """Build the .exe with PyInstaller."""
    clean()

    spec = BUILD_DIR / "pyinstaller.spec"
    if not spec.exists():
        print(f"❌ Spec not found: {spec}")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec), "--clean", "--noconfirm"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"❌ PyInstaller failed:\n{result.stderr}")
        sys.exit(1)

    print(f"✅ PyInstaller build complete — {APP_DIR}")


def bundle_browser() -> None:
    """Install Playwright browser for bundling."""
    browser_dir = ROOT / "browser"
    browser_dir.mkdir(exist_ok=True)

    result = subprocess.run(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("✅ Playwright Chromium installed")

    # Copy browser to dist
    playwright_src = Path.home() / ".cache" / "ms-playwright"
    if playwright_src.exists():
        for item in playwright_src.iterdir():
            if "chromium" in item.name.lower():
                dest = APP_DIR / "browser"
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
                print(f"✅ Browser bundled: {item.name}")
                return

    print("⚠️  Playwright browser cache not found — will download at runtime")


def run_innosetup() -> None:
    """Build the Windows installer with Inno Setup."""
    iscc = r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
    alt_iscc = r"C:\Program Files\Inno Setup 6\ISCC.exe"

    iscc_path = None
    for p in [iscc, alt_iscc]:
        if os.path.exists(p):
            iscc_path = p
            break

    if not iscc_path:
        print("⚠️  Inno Setup not found — skipping installer build")
        print("   Install from: https://jrsoftware.org/isdl.php")
        return

    iss_file = BUILD_DIR / "installer.iss"
    result = subprocess.run(
        [iscc_path, str(iss_file)],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"❌ Inno Setup failed:\n{result.stderr}")
        return

    print(f"✅ Installer built: {DIST / f'InsureDesk-Setup-{get_version()}.exe'}")


def verify() -> bool:
    """Verify the build output."""
    exe = APP_DIR / "InsureDesk.exe"
    if not exe.exists():
        print(f"❌ Build verification failed: {exe} not found")
        return False

    size_mb = exe.stat().st_size / (1024 * 1024)
    print(f"✅ Build verified: {exe.name} ({size_mb:.1f} MB)")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Build InsureDesk")
    parser.add_argument("--quick", action="store_true", help="PyInstaller only")
    parser.add_argument("--installer", action="store_true", help="PyInstaller + Inno Setup")
    parser.add_argument("--skip-deps", action="store_true", help="Skip pip install")
    args = parser.parse_args()

    print(f"🏗️  Building InsureDesk v{get_version()}")

    if not args.skip_deps:
        install_deps()

    run_pyinstaller()

    if not args.quick:
        bundle_browser()

    if args.installer:
        run_innosetup()

    verify()
    print(f"\n📁 Output: {DIST}")
    print(f"   Desktop: {APP_DIR / 'InsureDesk.exe'}")
    print(f"   CLI:     {DIST / 'InsureDesk-CLI' / 'InsureDesk-CLI.exe'}")

    if not args.quick:
        print(f"   Browser: {APP_DIR / 'browser' / 'chrome-win'}")


if __name__ == "__main__":
    main()
