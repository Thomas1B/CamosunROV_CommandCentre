# ui

The PySide6 windows. Everything you see on screen is built here.

| File or folder | What it does |
|---|---|
| `theme.py` | Colours, fonts and the `lab()` label helper used everywhere. |
| `widgets.py` | Custom-drawn gauges for the console (stick views, trigger and thruster bars, battery, the video pane with its HUD) and the controller map. |
| `assets/` | The program icon (`.ico`), logos and other images. |
| `menu/` | The main menu window and its cards. |
| `console/` | The console (main window) and its dialogs. |

## menu/

| File | What it does |
|---|---|
| `main_menu.py` | The main menu screen and its list of options. |
| `cards.py` | Shared building blocks for the cards: the card frame, title bar, maximise button, resize grip and button styles. |
| `connect.py` | CONNECT VEHICLE card. |
| `logs.py` | VIEW LOGS card. |
| `recordings.py` | VIEW RECORDINGS card, with its video view and seek bar. |
| `controller_map.py` | CONTROLLER MAP card. |
| `controller_profiles.py` | CONTROLLER PROFILES card (calibration), with its stick and trigger gauges. |

## console/

| File | What it does |
|---|---|
| `main_window.py` | The console: layout, arming, failsafes, event log and the control loop. |
| `reference_dialog.py` | The reference-value fields, shared by CONNECT VEHICLE and the console's File > Reference Values... dialog. |
| `exit_recording_dialog.py` | SAVE RECORDING? pop-up, shown on exit if REC was used. |
| `exit_log_dialog.py` | Session Log pop-up on exit (SAVE / EXPORT... / DISCARD). |

**Related settings in `config.py`:** `APP_VERSION`, `APP_BUILD`, `INTERNAL_TEMP_WARN_C`, `INTERNAL_TEMP_CLEAR_C`, and the hold times `ARM_HOLD_S`, `ZERO_HOLD_S`, `ZERO_CLEAR_HOLD_S`, `MARK_REPEAT_S`.
