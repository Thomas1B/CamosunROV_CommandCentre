# command_center_py

All of the command centre's code. `rov_console.py` at the top of the repo only starts it:

```
py rov_console.py
```

See the main `README.md` at the top of the repo for setup and how to use the program.

## Folders

| Folder | What it does | Details |
|---|---|---|
| `vehicle/` | Talking to the ROV: UDP link to the Pi, thruster mixing, Bar30 reference values, saved vehicle profiles | [vehicle/README.md](vehicle/README.md) |
| `controller/` | The game controller: reading it, calibration profiles, the simulated demo controller | [controller/README.md](controller/README.md) |
| `video/` | The camera: live feed, REC, playing and exporting recordings | [video/README.md](video/README.md) |
| `logs/` | The session event log: writing, reading back, exporting, file names | [logs/README.md](logs/README.md) |
| `ui/` | Everything on screen: the main menu, its cards, the console and its dialogs | [ui/README.md](ui/README.md) |

## Files

| File | What it does |
|---|---|
| `app.py` | Starts the program and switches between the main menu and the console. It owns the one shared controller reader, sets the window icon, and loads PyAV in the background once the menu is on screen. |
| `config.py` | All the tuning constants in one place: version, network defaults, rates, deadzones, gain steps, camera tilt limits, hold times, temperature limits, thruster names and the folders used for saved files. Change settings here, not in the other files. |
| `__init__.py` | Marks the folder as a Python package. |

## How it fits together

```
rov_console.py
  -> app.py
       -> ui/menu/main_menu.py      main menu (CONNECT VEHICLE, DEMO MODE, VIEW LOGS, ...)
       -> ui/console/main_window.py the console, once connected or in DEMO MODE
            controller/   read the controller           (about 250 times a second)
            vehicle/      mix the sticks into thrust,
                          send commands to the Pi        (RATE_HZ, 50 times a second)
                          and receive telemetry
            video/        show the camera feed and record it
            logs/         save every event-log line to logs/
```

Closing the console (only allowed while disarmed) returns to the main menu.

## Saved files

The program reads and writes these folders at the top of the repo, next to `rov_console.py`, not inside `command_center_py`. They are all git-ignored.

| Folder | Contents | Code |
|---|---|---|
| `vehicle_profiles/` | One JSON file per vehicle | `vehicle/profiles.py` |
| `controller_profiles/` | One JSON file per controller calibration | `controller/profiles.py` |
| `logs/` | One CSV file per console session | `logs/event_log.py` |
| `recordings/` | One MKV file per REC recording | `video/receiver.py` (writes), `video/recordings.py` (reads) |

## Where to change things

| To change | Look in |
|---|---|
| A setting (ports, rates, deadzones, limits, thruster names) | `config.py` |
| How the sticks map to the thrusters | `vehicle/mixer.py` |
| The command or telemetry packet format (must match the Pi) | `vehicle/link.py` |
| Colours and fonts | `ui/theme.py` |
| The console layout | `ui/console/main_window.py` |
| A main menu card | `ui/menu/` |

## __pycache__

Python's compiled copies of the files, made automatically. Safe to delete at any time, and ignored by git.
