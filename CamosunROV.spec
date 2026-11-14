# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller build recipe for the Camosun ROV Command Centre.

A .spec file is a normal Python script that PyInstaller runs. It replaces a long
"pyinstaller ..." command line, so every build uses the same settings.

Build (venv activated, from the repo root - the folder this file is in):
    pyinstaller --noconfirm CamosunROV.spec

Output:
    dist/CamosunROV/CamosunROV.exe          <- double-click this to test
    dist/CamosunROV/_internal/              <- Python, Qt, FFmpeg, SDL2, our code (don't touch)
    dist/CamosunROV/vehicle_profiles/       <- only the profiles listed in SHIP_PROFILES below
    dist/CamosunROV/controller_profiles/    <- only the profiles listed in SHIP_PROFILES below

logs/ and recordings/ are NOT shipped: the program creates them next to the .exe
the first time it saves a log or recording.

--noconfirm wipes dist/CamosunROV/ on every build, including any logs, recordings or
profiles you saved while testing the built .exe.

PyInstaller also makes a build/ folder (temporary working files). It can be deleted
at any time; both build/ and dist/ are in .gitignore.
"""

import shutil              # file copying (used for the shipped profiles at the bottom)
from pathlib import Path   # path handling that works with / on Windows too

# ===========================================================================
# SETTINGS - the parts you are likely to change
# ===========================================================================

# Name of the .exe and of its folder in dist/  ->  i.e: dist/CamosunROV/CamosunROV.exe
APP_NAME = "CamosunROV"

# SPECPATH is provided by PyInstaller: the folder this .spec file is in (the repo root).
# Every path below is built from ROOT, so the build works no matter which folder
# the terminal is in.
ROOT = Path(SPECPATH)

# Program icon for the .exe file itself (Explorer, desktop shortcut).
# Must be the same file app.py loads for the window/taskbar icon (ICON_ICO in app.py).
ICON = ROOT / "command_center_py" / "ui" / "assets" / "CamosunROV_Logo.ico"

# ---------------------------------------------------------------------------
# PROFILES SHIPPED WITH THE BUILD
# Each line is a profile file in this repo, copied to the same place next to
# CamosunROV.exe. To add one: save it from the app, then add its line here.
# To remove one: delete (or # comment out) its line. Ship none: SHIP_PROFILES = []
# Rebuild after any change.
# ---------------------------------------------------------------------------
SHIP_PROFILES = [
    "vehicle_profiles/ROV-01.json",
]

# ===========================================================================
# BUILD STEPS - PyInstaller runs these four in order:
#   Analysis -> PYZ -> EXE -> COLLECT
# ===========================================================================

# 1: Analysis: start at rov_console.py and follow every import (our command_center_py
#    package, PySide6, pygame, av, openpyxl, ...) to find every Python module and
#    DLL the program needs.
a = Analysis(
    [str(ROOT / "rov_console.py")],   # the entry script - the same file you run with "py rov_console.py"
    pathex=[str(ROOT)],               # extra folder to search for imports (so command_center_py is found)
    # Non-Python files the code loads at run time. Analysis only follows imports, so it
    # can't find these on its own. Format: (source folder, folder inside _internal/).
    # The destination matches the source path so app.py, theme.py and main_menu.py,
    # which find assets relative to their own file, still find them in the build.
    datas=[(str(ROOT / "command_center_py" / "ui" / "assets"), "command_center_py/ui/assets")],
    hiddenimports=[],   # modules PyInstaller misses (imported by string, etc.) - add here if
                        # the built .exe says "ModuleNotFoundError: No module named ..."
    excludes=[],        # modules to leave out on purpose (to shrink the build) - none for now
)

# 2: PYZ: pack all the pure-Python modules Analysis found (our code + libraries)
#    into one compressed archive inside _internal/.
pyz = PYZ(a.pure)

# 3: EXE: build CamosunROV.exe - a small launcher that starts Python and runs
#    rov_console.py from the PYZ archive.
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # folder build: DLLs go in _internal/, not inside the .exe
    name=APP_NAME,
    icon=str(ICON),
    console=True,            # keep the terminal window for debug prints; False hides it
    upx=False,               # UPX compression triggers antivirus false positives
)

# 4: COLLECT: put the .exe, the DLLs (Qt, FFmpeg, SDL2, Python) and the data files
#    together in dist/CamosunROV/ - this folder is the finished program.
coll = COLLECT(
    exe,
    a.binaries,   # DLLs / .pyd files found by Analysis
    a.datas,      # the assets folder from datas= above (plus data files libraries need)
    name=APP_NAME,
    upx=False,    # same reason as in EXE
)

# ===========================================================================
# AFTER THE BUILD - copy the shipped profiles next to the .exe
# ===========================================================================
# config.py looks for vehicle_profiles/ and controller_profiles/ next to the .exe
# when frozen (TOP_DIR), not inside _internal/. datas= above would put them in
# _internal/, so they are copied here by hand instead.

# DISTPATH is provided by PyInstaller: the dist/ folder.
out_dir = Path(DISTPATH) / APP_NAME   # dist/CamosunROV/

for rel in SHIP_PROFILES:
    src = ROOT / rel                  # e.g. <repo>/vehicle_profiles/ROV-01.json
    # Stop the build with a clear message if a listed profile doesn't exist
    # (the profile folders are in .gitignore, so a fresh clone won't have them).
    if not src.is_file():
        raise SystemExit(f"SHIP_PROFILES: {rel} not found in the repo - "
                         f"save it from the app first, or remove its line from CamosunROV.spec")
    dst = out_dir / rel               # e.g. dist/CamosunROV/vehicle_profiles/ROV-01.json
    dst.parent.mkdir(parents=True, exist_ok=True)   # create vehicle_profiles/ etc. if needed
    shutil.copy2(src, dst)            # copy the file (copy2 also keeps its modified date)
    print(f"Shipped profile: {rel}")