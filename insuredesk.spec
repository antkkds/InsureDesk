# -*- mode: python ; coding: utf-8 -*-
"""InsureDesk Bridge — PyInstaller build spec.

Build command:
    cd InsureDesk && pyinstaller insuredesk.spec --clean

Output:
    dist/InsureDeskBridge/     # One-folder bundle (works on all platforms)
        InsureDeskBridge.exe   # or InsureDeskBridge (Linux/Mac)
        profiles/              # Portal YAML profiles
"""

import sys
from pathlib import Path

PROJECT_DIR = Path.cwd()
SRC_DIR = PROJECT_DIR / "src"
PROFILES_DIR = PROJECT_DIR / "profiles"

# Collect YAML profile files
profile_datas = []
if PROFILES_DIR.exists():
    for f in sorted(PROFILES_DIR.iterdir()):
        if f.suffix in (".yaml", ".yml"):
            profile_datas.append((str(f), "profiles"))

# Source packages to bundle
src_packages = [
    "src/bridge",
    "src/portal",
    "src/quote",
    "src/tools",
    "src/policy",
    "src/runtime",
    "src/portals",
    "src/browser",
    "src/drivers",
    "src/database",
    "src/models",
    "src/customers",
    "src/documents",
]

src_datas = []
for pkg in src_packages:
    pkg_path = PROJECT_DIR / pkg
    if pkg_path.exists():
        src_datas.append((str(pkg_path), pkg))

block_cipher = None

a = Analysis(
    ['run_bridge.py'],
    pathex=[str(PROJECT_DIR)],
    binaries=[],
    datas=profile_datas,
    hiddenimports=[
        'sqlalchemy',
        'sqlalchemy.ext.declarative',
        'yaml',
        'src.bridge.server',
        'src.bridge.protocol',
        'src.portal.errors',
        'src.quote.field_mapper',
        'src.quote.portal_executor',
        'src.tools.registry',
        'src.tools.base',
        'src.tools.insurance.quote_tools',
        'src.tools.insurance.customer_tools',
        'src.policy.engine',
        'src.runtime.session_runtime',
        'src.portals.base',
        'src.portals.great_eastern',
        'src.browser.driver',
        'src.browser.foundation',
        'src.browser.recovery',
        'src.database.db_manager',
        'src.database.models',
        'src.models.adapter_registry',
        'src.models.adapter_base',
        'src.quote.mock',
        'src.quote.models',
        'src.quote.base',
    ],
    hookspath=[],
    hooksconfig={},
    excludes=[
        'PySide6',
        'PyQt5',
        'PyQt6',
        'matplotlib',
        'tkinter',
        'PIL',
        'cv2',
        'scipy',
        'notebook',
        'jupyter',
        'pandas',
        'numpy',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.zipped_data,
    a.binaries,
    a.datas,
    [],
    name='InsureDeskBridge',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_tracker=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
