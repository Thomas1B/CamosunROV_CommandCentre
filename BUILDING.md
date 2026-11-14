# Building the CamosunROV Command Centre .exe

## Overview

The Command Centre is packaged with [PyInstaller](https://pyinstaller.org) into a standalone Windows program. The result is a folder, `dist\CamosunROV\`, that runs on any 64-bit Windows 10/11 laptop without Python installed.

All build settings live in `CamosunROV.spec` in the repo root, so every build comes out the same. The build produces:

```
dist/CamosunROV/
├── CamosunROV.exe       <- double-click to run
├── _internal/           <- Python, Qt, FFmpeg, SDL2, our code (don't touch)
├── vehicle_profiles/    <- profiles listed in SHIP_PROFILES
├── logs/                <- empty; the app saves session logs here
└── recordings/          <- empty; the app saves camera recordings here
```

The build also creates a temporary `build/` folder. Both `build/` and `dist/` are in `.gitignore`.

## One-time setup

Once per computer, on Windows.

1. Clone the repo and create the project's `.venv` as described in the README. Skip this if you already have the repo and its `.venv` set up.
2. Open a terminal in the repo root. In VS Code: **Terminal → New Terminal** (Ctrl+`).
3. Activate the venv:

   ```
   .venv\Scripts\activate
   ```

   `(.venv)` should appear at the start of the prompt.
4. If PowerShell shows *"running scripts is disabled on this system"*, run this once, then repeat step 3:

   ```
   Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
   ```
5. Install the app's packages plus PyInstaller, then check the version:

   ```
   python -m pip install -r build_requirements.txt
   python -m pip show pyinstaller
   ```

   It should say `Version: 6.21.0`, matching `build_requirements.txt`.

## Build

1. In the repo root, activate the venv if it isn't already (no `(.venv)` at the start of the prompt):

   ```
   .venv\Scripts\activate
   ```
2. Build (1–2 min):

   ```
   pyinstaller --noconfirm CamosunROV.spec
   ```

   It should end with `Shipped profile: ...` and `Shipped empty folder: ...` lines, then `Build complete!`

   Remove `--noconfirm` if you want PyInstaller to ask before deleting the old build.
3. In File Explorer, open the repo's `dist\CamosunROV\` folder and double-click **CamosunROV.exe**.

## Other settings in the spec

| Setting | What it does |
| --- | --- |
| `APP_NAME` | Name of the .exe and its folder. Keep it without spaces. |
| `ICON` | The .exe icon. Must match `ICON_ICO` in `app.py`. |
| `console=False` | Hides the terminal window. Set `True` to see debug output (packets lost, controller errors). |
| `hiddenimports=[]` | Add a module here if the .exe says `ModuleNotFoundError`. |

## Notes

- Never move or edit anything in `_internal\`.
- The .exe only runs with `_internal\` beside it. To share the app, copy or zip the whole `CamosunROV` folder.
- Desktop shortcuts to the .exe work. A copy of the .exe alone does not.
