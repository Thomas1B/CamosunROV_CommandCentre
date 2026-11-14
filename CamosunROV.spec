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
    install.bat, uninstall.bat - from SHIP_SCRIPTS

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
    icon=str(ICON),          # icon shown on the .exe in Explorer and on shortcuts
    console=False,           # show terminal for debug; False hides it
    upx=False,               # UPX triggers antivirus false positives
)

# 4: COLLECT - gather everything into dist/CamosunROV/
coll = COLLECT(
    exe,            # the launcher from step 3 -> CamosunROV.exe
    a.binaries,     # DLLs and .pyd files (Python, Qt, FFmpeg, SDL2) -> _internal/
    a.datas,        # data files (our UI assets + files libraries need) -> _internal/
    name=APP_NAME,  # output folder name -> dist/CamosunROV/
    upx=False,      # no UPX compression on the DLLs either (antivirus)
)

# ===========================================================================
# AFTER THE BUILD - copy SHIP_PROFILES and SHIP_SCRIPTS, create SHIP_EMPTY_FOLDERS next to the .exe
# (config.py looks there when frozen, not in _internal/)
# ===========================================================================

out_dir = Path(DISTPATH) / APP_NAME   # dist/CamosunROV/ (DISTPATH set by PyInstaller)

for rel in SHIP_PROFILES:
    src = ROOT / rel
    if not src.is_file():   # profile folders are gitignored, so a fresh clone may lack them
        raise SystemExit(f"SHIP_PROFILES: {rel} not found in the repo - "
                         f"save it from the app first, or remove its line from CamosunROV.spec")
    dst = out_dir / rel
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"Shipped profile: {rel}")

for folder in SHIP_EMPTY_FOLDERS:
    (out_dir / folder).mkdir(parents=True, exist_ok=True)   # create dist/CamosunROV/<folder>/
    print(f"Shipped empty folder: {folder}")

for rel in SHIP_SCRIPTS:
    src = ROOT / rel
    if not src.is_file():
        raise SystemExit(f"SHIP_SCRIPTS: {rel} not found in the repo")
    shutil.copy2(src, out_dir / src.name)   # installer/install.bat -> dist/CamosunROV/install.bat
    print(f"Shipped script: {src.name}")