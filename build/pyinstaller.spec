# -*- mode: python -*-
"""
InsureDesk PyInstaller Spec

Build a single .exe that bundles the engine, desktop GUI,
portal YAML profiles, and default configuration.

Usage:
    pyinstaller build/pyinstaller.spec --clean
"""

import os
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────
import os
HERE = Path(os.getcwd()) / "build"
ROOT = HERE.parent

# ── Version ────────────────────────────────────────────────────
VERSION_FILE = HERE / "version.txt"
VERSION = open(VERSION_FILE).read().strip() if VERSION_FILE.exists() else "1.0.0"

# ── Data files to bundle ───────────────────────────────────────
_DATA_FILES = []

# Portal YAML profiles
profiles_src = ROOT / "portals"
if profiles_src.exists():
    for f in profiles_src.rglob("*"):
        if f.is_file() and f.suffix in (".yaml", ".yml"):
            dest = str(f.relative_to(ROOT).parent)
            _DATA_FILES.append((str(f), dest))

# Default config
config_yaml = ROOT / "config" / "agent.yaml"
if config_yaml.exists():
    _DATA_FILES.append((str(config_yaml), "config"))

# Version file
_VERSION_FILES = [(str(VERSION_FILE), "build")]

# External plugins (copied alongside the exe)
PLUGINS_SRC = ROOT / "plugins"
if PLUGINS_SRC.exists():
    for f in PLUGINS_SRC.rglob("*"):
        if f.is_file():
            dest = str(f.relative_to(ROOT).parent)
            _DATA_FILES.append((str(f), dest))

# Hidden imports for CLI
_HIDDEN = [
    "build.version",
]

# ── Hidden imports (auto-detected may miss some) ──────────────
_HIDDEN_IMPORTS = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PySide6.QtNetwork",
    "cryptography",
    "keyring",
    "keyring.backends",
    "yaml",
    "playwright",
    "sqlalchemy",
    "sqlalchemy.ext.declarative",
    "sqlalchemy.orm",
    "alembic",
    "dateutil",
    # Core plugin system (NOT document_intelligence — that's external)
    "src.plugins",
    "src.plugins.base",
    "src.plugins.registry",
]

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=_DATA_FILES + _VERSION_FILES,
    hiddenimports=_HIDDEN_IMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        # Excluded: document-intelligence SDK (external plugin)
        "document_intelligence",
        "document_intelligence.core",
        "document_intelligence.importer",
        "document_intelligence.normalize",
        "document_intelligence.storage",
        "document_intelligence.index",
        # Excluded: PyMuPDF (part of external plugin)
        "fitz",
        "pymupdf",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="InsureDesk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window for desktop app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "build" / "insuredesk.ico") if (ROOT / "build" / "insuredesk.ico").exists() else None,
)

# Also build a CLI version with console
exe_cli = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="InsureDesk-CLI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Console window for CLI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# COLLECT for one-folder packaging (easier to bundle with Inno Setup)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="InsureDesk",
)

coll_cli = COLLECT(
    exe_cli,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="InsureDesk-CLI",
)
