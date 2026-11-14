# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build recipe for the Camosun ROV Command Centre.
Builds a exe program of the command centre.

Build (venv activated, from the repo root):
    pyinstaller --noconfirm CamosunROV.spec

Output: dist/CamosunROV/
    CamosunROV.exe   - run this
    _internal/       - Python, Qt, FFmpeg, SDL2, our code (don't touch)
    *_profiles/      - only the profiles in SHIP_PROFILES
    logs/, recordings/ - empty folders from SHIP_EMPTY_FOLDERS

--noconfirm wipes dist/CamosunROV/ on every build.
"""

import shutil
from pathlib import Path

# ===========================================================================
# SETTINGS
# ===========================================================================

APP_NAME = "CamosunROV"   # .exe and folder name; keep it without spaces
ROOT = Path(SPECPATH)     # repo root (SPECPATH = this file's folder, set by PyInstaller)

# .exe icon - must match ICON_ICO in app.py
ICON = ROOT / "command_center_py" / "ui" / "assets" / "CamosunROV_Logo.ico"

# Profiles copied next to the .exe. Add/remove lines, then rebuild. None: []
SHIP_PROFILES = [
    "vehicle_profiles/ROV-01.json",
]

# Empty folders created next to the .exe. Add/remove names, then rebuild. None: []
SHIP_EMPTY_FOLDERS = [
    "logs",
    "recordings",
]

# ===========================================================================
# BUILD STEPS: Analysis -> PYZ -> EXE -> COLLECT
# ===========================================================================

# 1: Analysis - follow imports from rov_console.py to find every module and DLL
a = Analysis(
    [str(ROOT / "rov_console.py")],   # entry script
    pathex=[str(ROOT)],               # so command_center_py is found
    # non-Python files: (source, destination inside _internal/)
    datas=[(str(ROOT / "command_center_py" / "ui" / "assets"), "command_center_py/ui/assets")],
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
    name=APP_NAME,           # file name of the launcher -> CamosunROV.exe
    icon=str(ICON),          # icon shown on the .exe in Explorer