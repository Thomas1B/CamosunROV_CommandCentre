# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build recipe for the Camosun ROV Command Centre.
Builds a exe program of the command centre.

Build (venv activated, from the repo root):
    pyinstaller --noconfirm CamosunROV.spec

Output: dist/CamosunROV_V<version>/  (version from config.py APP_VERSION, e.g. CamosunROV_V2.0.0)
    CamosunROV_V<version>.exe   - run this
    _internal/       - Python, Qt, FFmpeg, SDL2, our code, LICENSE, default vehicle profiles (don't touch)
    install.bat, uninstall.bat - from SHIP_SCRIPTS

User data (profiles, logs, recordings) is not in the build: the program uses
C:/Users/Public/Documents/CamosunROV_Data (config.py DATA_DIR) and copies the default
vehicle profiles there on its first start of each version.

--noconfirm wipes dist/CamosunROV_V<version>/ on every build.
The build time is printed at the end.
"""

import shutil
import time
from pathlib import Path
import sys

BUILD_START = time.perf_counter()   # start the build timer (seconds)

sys.path.insert(0, str(Path(SPECPATH)))                 # so the spec can read config.py
from command_center_py.config import APP_VERSION

# ===========================================================================
# SETTINGS
# ===========================================================================

APP_NAME = f"CamosunROV_V{APP_VERSION}"   # .exe and folder name, e.g. CamosunROV_V2.0.0; keep it without spaces
ROOT = Path(SPECPATH)     # repo root (SPECPATH = this file's folder, set by PyInstaller)

# .exe icon - must match ICON_ICO in app.py
ICON = ROOT / "command_center_py" / "ui" / "assets" / "CamosunROV_Logo.ico"

# Default vehicle profiles: every .json in command_center_py/defaults/vehicle_profiles/ is
# bundled. Add or remove files there, then rebuild.

# Repo files copied next to the .exe (by file name only). Add/remove lines, then rebuild.
SHIP_SCRIPTS = []

# ===========================================================================
# BUILD STEPS: Analysis -> PYZ -> EXE -> COLLECT
# ===========================================================================

# 1: Analysis - follow imports from rov_console.py to find every module and DLL
a = Analysis(
    [str(ROOT / "rov_console.py")],   # entry script
    pathex=[str(ROOT)],               # so command_center_py is found
    # non-Python files: (source, destination inside _internal/)
    datas=[
        (str(ROOT / "command_center_py" / "ui" / "assets"), "command_center_py/ui/assets"),
        (str(ROOT / "command_center_py" / "defaults"), "command_center_py/defaults"),   # default profiles
        (str(ROOT / "LICENSE"), "."),                                                  # ABOUT shows it
    ],
    hiddenimports=[],   # add a module here if the .exe says ModuleNotFoundError
    excludes=[],
)

# 2: PYZ - pack the Python modules into one archive
pyz = PYZ(a.pure)

# 3: EXE - the launcher
exe = EXE(
    pyz,                     # the archive of our Python code + libraries (step 2)
    a.scripts,               # the entry script (rov_console.py) the launcher runs first
    [],                      # Python run-time options passed at start-up - none
    exclude_binaries=True,   # folder build: DLLs go in _internal/, not inside the .exe
    name=APP_NAME,           # file name of the launcher -> CamosunROV_V2.0.0.exe
    icon=str(ICON),          # icon shown on the .exe in Explorer and on shortcuts
    console=False,           # show terminal for debug; False hides it
    upx=False,               # UPX triggers antivirus false positives
)

# 4: COLLECT - gather everything into dist/CamosunROV_V2.0.0/
coll = COLLECT(
    exe,            # the launcher from step 3 -> CamosunROV_V2.0.0.exe
    a.binaries,     # DLLs and .pyd files (Python, Qt, FFmpeg, SDL2) -> _internal/
    a.datas,        # data files (our UI assets + files libraries need) -> _internal/
    name=APP_NAME,  # output folder name -> dist/CamosunROV_V2.0.0/
    upx=False,      # no UPX compression on the DLLs either (antivirus)
)

# ===========================================================================
# AFTER THE BUILD - copy SHIP_SCRIPTS next to the .exe
# ===========================================================================

out_dir = Path(DISTPATH) / APP_NAME   # dist/CamosunROV_V2.0.0/ (DISTPATH set by PyInstaller)

for rel in SHIP_SCRIPTS:
    src = ROOT / rel
    if not src.is_file():
        raise SystemExit(f"SHIP_SCRIPTS: {rel} not found in the repo")
    shutil.copy2(src, out_dir / src.name)   # installer/install.bat -> dist/CamosunROV_V2.0.0/install.bat
    print(f"Shipped script: {src.name}")

# ===========================================================================
# BUILD TIME
# ===========================================================================

build_s = time.perf_counter() - BUILD_START
print(f"\nBuilt {APP_NAME} in {build_s:.1f} s ({int(build_s // 60)} min {build_s % 60:.0f} s)")
