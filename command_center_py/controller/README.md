# controller

Reads the game controller and turns it into clean stick, trigger and button values.

| File | What it does |
|---|---|
| `gamepad.py` | Reads the controller with SDL (pygame-ce) in its own thread at 250 Hz. `Gamepad.snapshot()` returns a `PadState` with the latest sticks, triggers and buttons. |
| `profiles.py` | Controller profiles: saving and loading the calibration files in `controller_profiles/`, and `CalibratedPad`, which applies a profile's centre, deadzone and range to the raw values. |
| `demo_pad.py` | A simulated controller for DEMO MODE when no real one is plugged in. It runs a fixed script (arm, sweep the sticks, change gain, tilt the camera and so on). |

**Used by:** `app.py` (one shared `Gamepad`), the console (`ui/console/main_window.py`), and the CONNECT VEHICLE and CONTROLLER PROFILES cards.

**Related settings in `config.py`:** `CONTROLLER_LAYOUT`, `DEADZONE`, `TRIGGER_DEADZONE`, `DEMO_SIM_PAD`, `CONTROLLER_PROFILES_DIR`.
