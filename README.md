# CamosunROV Command Centre

Pilot command centre for the Camosun capstone underwater ROV.

The command centre is a Windows desktop application the pilot uses to operate the
ROV. It reads a game controller (e.g. PlayStation DualShock 3), mixes the stick and trigger
inputs into commands for the ROV's six thrusters and camera tilt servo, and
sends them over the tether to the ROV's Raspberry Pi, which passes them on to
the STM32 motor controller.

In the other direction, it receives telemetry from the Pi and displays it:
depth, pressure, water and internal temperature, orientation, battery voltage
and current, and the leak sensor.

Main features:

- Arm/disarm and an emergency stop (controller or keyboard SPACE)
- Adjustable thrust gain (25 / 50 / 75 / 100 %)
- Failsafes: the ROV is automatically disarmed if the controller disconnects or the tether link is lost
- Leak alarm and high internal temperature warning, plus an event log with operator marks
- Main menu: connect to a vehicle (with saved vehicle profiles), demo mode, controller maps
- Demo mode with simulated telemetry, for testing without the ROV
- Camera view with HUD (the live video stream is not wired in yet)

---

## Program Requirements

### Computer

- Windows 10 or 11 (64-bit)
- An Ethernet (RJ45) port for the ROV tether. A USB-to-Ethernet adapter also works.

### Controller

- PlayStation DualShock 3 controller, connected by USB cable
- **DsHidMini driver:** Windows has no built-in driver for the DualShock 3, so
  download and install DsHidMini from
  [docs.nefarius.at/Downloads](https://docs.nefarius.at/Downloads/) before
  plugging in the controller.

> **Note:** Xbox controller support is planned. For now, only the DualShock 3
> is supported.

### Software

- Python 3.14 and the project venv. See [Developer Setup](#developer-setup).

> **Note:** We plan to release the command centre as a Windows executable
> (`.exe`), so pilots will be able to run it without installing Python.

---

## Developer Setup

### Python setup (Windows)

The command centre runs on **Python 3.14** inside a virtual environment
(`.venv`) in the top directory of this repo. That folder is
**not** committed - each person builds their own from `py_requirements.txt`,
which pins exact package versions so everyone's environment is identical.

#### 1. Install Python 3.14 (once)

3.14 installs alongside any other Python versions you already have; it will not
replace them.

- Recommended: install the Python install manager from python.org, then run
  `py install 3.14`
- Or use the classic python.org 3.14 installer (untick "Add to PATH" if you
  don't want 3.14 to become your default `python`).

Check it is available:

```
py -0
```

This lists the installed Python versions; 3.14 should appear.

#### 2. Create the venv (once, from the repo's top directory)

```
py -3.14 -m venv .venv
```

Use `py -3.14`, not `python` - plain `python` may build the venv with a
different version.

#### 3. Activate it and install dependencies

##### 3a. Activate the venv

```
.venv\Scripts\activate
```

Your prompt should now start with `(.venv)`.

##### 3b. Check the Python version

```
python --version
```

This must print `Python 3.14.x`. If it doesn't, delete the `.venv` folder and
repeat step 2.

##### 3c. Install the dependencies

```
python -m pip install -r py_requirements.txt
```

#### 4. Run the console

```
py rov_console.py
```

No options - the program opens on the main menu:

- **CONNECT VEHICLE** - enter the Pi's IP address and UDP ports (or load a saved
  profile) and press CONNECT. The console opens once the Pi answers; if there is
  no answer within 5 s the dialog stays open so you can check the tether and retry.
  **SAVE PROFILE** stores the settings in `vehicle_profiles/` (one JSON file per vehicle).
- **DEMO MODE** - simulated vehicle, nothing is transmitted.
- **CONTROLLER MAP** - DualShock 3 and Xbox button maps.
- **QUIT** - exit.

Closing the console window (or File > Back to Main Menu) returns to the main menu,
but only while the ROV is **disarmed**. Ctrl+C in the terminal disarms and exits.

#### Day-to-day

- Activate the venv (`.venv\Scripts\activate`) in each new terminal before running.
- After pulling, if `py_requirements.txt` changed, re-run
  `python -m pip install -r py_requirements.txt`.
- Something broken? Delete the `.venv` folder and repeat steps 2-3.
- Adding/upgrading a package: pin the exact version in `py_requirements.txt`,
  install, test, and commit the file.
