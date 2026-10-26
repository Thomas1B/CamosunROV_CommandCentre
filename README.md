# CamosunROV Command Centre

Pilot command centre for the Camosun capstone underwater ROV.

> **Note:** We plan to release the command centre as a Windows executable
> (`.exe`) that runs without installing Python. Until then, set it up and run it
> by following [Developer Setup](#developer-setup), then
> [Tether Network Setup](#tether-network-setup).

The command centre is a Windows desktop application the pilot uses to operate the
ROV. It reads a game controller (PlayStation DualShock 3 or Xbox), mixes the stick and trigger
inputs into commands for the ROV's six thrusters and camera tilt servo, and
sends them over the tether to the ROV's Raspberry Pi, which passes them on to
the STM32 motor controller.

In the other direction, it receives telemetry and the live camera stream from
the Pi and displays them: depth, pressure, water and internal temperature,
orientation (roll, pitch, heading), battery voltage with an estimated charge
level, the leak sensor, and link quality (round-trip time and packet loss).

Main features:

- Arm/disarm and an emergency stop (controller, keyboard SPACE, or the Vehicle menu)
- Adjustable thrust gain (25 / 50 / 75 / 100 %)
- Live camera view (H.264 over UDP, decoded with PyAV) with a HUD; shows
  *VIDEO LOST* over the last frame if the stream stops for 1.5 s
- Failsafes: the ROV is automatically disarmed if the controller disconnects,
  the tether link is lost, or a leak is detected
- No keyboard control of the ROV except SPACE for E-STOP
- Leak alarm with recovery: after a leak the thrusters are disarmed and the
  camera tilt is locked until the STM32 confirms the leak sensor is dry
- High internal temperature warning (above 45 °C)
- Depth zero: take the current depth as 0 m (display only) and clear it again
- Bar30 depth sensor reference values (surface pressure, water density,
  second-order calibration), sent to the Pi/STM32 and confirmed by it
- Event log with operator marks
- Main menu: connect to a vehicle (with saved vehicle profiles), demo mode, controller maps
- Demo mode with a simulated vehicle, a simulated controller and simulated
  packet loss, for testing without the ROV

---

## Program Requirements

### Computer

- Windows 10 or 11 (64-bit)
- An Ethernet (RJ45) port for the ROV tether. A USB-to-Ethernet adapter also works.
  The port needs a static IP address. See [Tether Network Setup](#tether-network-setup).

### Controller

One of:

- PlayStation DualShock 3 controller, connected by USB cable
  - **DsHidMini driver:** Windows has no built-in driver for the DualShock 3, so
    download and install DsHidMini from
    [docs.nefarius.at/Downloads](https://docs.nefarius.at/Downloads/) before
    plugging in the controller.
- Xbox controller. Windows has the driver built in.

Switch the on-screen button names to match with the DUALSHOCK 3 / XBOX toggle
above STICK INPUT in the console.

### Software

- Python 3.14 and the project venv. See [Developer Setup](#developer-setup).

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

- **CONNECT VEHICLE** - enter the vehicle name, the Pi's IP address, the UDP
  ports (command, telemetry and video) and the Bar30 reference values, or load
  a saved profile, then press CONNECT. The console opens once the Pi answers; if
  there is no answer within 5 s the dialog stays open so you can check the
  tether and retry. **SAVE PROFILE** stores the settings in `vehicle_profiles/`
  (one JSON file per vehicle); **DELETE** removes the selected profile.
- **DEMO MODE** - simulated vehicle, nothing is transmitted.
- **CONTROLLER MAP** - DualShock 3 and Xbox button maps.
- **QUIT** - exit.

Navigate the menu with the arrow keys and Enter, or with the controller (D-pad,
CROSS to select, CIRCLE to go back).

Closing the console window (or File > Back to Main Menu) returns to the main menu,
but only while the ROV is **disarmed**. Ctrl+C in the terminal disarms, sends
zero-thrust frames and exits; press it a second time to force-quit if the clean
shutdown hangs.

The program refuses to start outside the `.venv` or on a Python version other
than 3.14, and tells you which setup step to repeat.

#### Day-to-day

- Activate the venv (`.venv\Scripts\activate`) in each new terminal before running.
- After pulling, if `py_requirements.txt` changed, re-run
  `python -m pip install -r py_requirements.txt`.
- Something broken? Delete the `.venv` folder and repeat steps 2-3.
- Adding/upgrading a package: pin the exact version in `py_requirements.txt`,
  install, test, and commit the file.

---

## Tether Network Setup

Once the program is installed, set up the laptop's tether connection. The
laptop and the ROV's Raspberry Pi talk over the Fathom tether as a small
two-device network. There is no router and no DHCP server on it, so both ends
use fixed IP addresses. Do this once per laptop.

| Device | IP address | Subnet mask | Receives on |
|---|---|---|---|
| Raspberry Pi (`eth0`) | `192.168.2.2` | `255.255.255.0` (/24) | UDP 5600 (commands) |
| Command centre laptop | `192.168.2.1` | `255.255.255.0` (/24) | UDP 5601 (telemetry), UDP 5602 (video) |

The Pi side is already set up by `setup_pi.sh` in CamosunROV_Pi (the
`rov-tether` NetworkManager profile). Only the laptop needs the steps below.

### 1. Plug in the tether

Connect the tether to the laptop's Ethernet port (or USB-to-Ethernet adapter)
and power the ROV, so Windows shows the adapter as connected. The link light on
the port should come on once the Pi has booted.

> **Tip:** If you use the laptop's built-in Ethernet port for internet
> elsewhere, a separate USB-to-Ethernet adapter kept just for the tether saves
> you switching the setting back and forth. Each adapter keeps its own IP settings.

### 2. Give the adapter a static IP

1. Press **Win + R**, type `ncpa.cpl`, and press Enter.
2. Find the tether adapter (usually *Ethernet* or *Ethernet 2*; unplugging the
   tether shows which one it is). Right-click it > **Properties**.
3. Select **Internet Protocol Version 4 (TCP/IPv4)** > **Properties**.
4. Choose **Use the following IP address** and enter:
   - IP address: `192.168.2.1`
   - Subnet mask: `255.255.255.0`
   - Default gateway: *leave blank* (with no gateway on the tether, Windows
     keeps sending internet traffic over Wi-Fi)
5. Leave both DNS server boxes **blank**. Click **OK**, then **Close**.

To undo it later, go back to the same window and choose **Obtain an IP address
automatically**.

### 3. Allow telemetry and video through the firewall

Windows treats a direct cable link as an *Unidentified network* and puts it in
the **Public** firewall profile, which blocks incoming UDP. In an
**Administrator** PowerShell:

```
New-NetFirewallRule -DisplayName "CamosunROV UDP in" -Direction Inbound -Protocol UDP -LocalPort 5601,5602 -Action Allow -Profile Any
```

`-Profile Any` matters: a rule for Private only would not apply to the tether.

**Remove any Python block rules.** If the Windows "Allow access?" pop-up for
Python was ever closed or missed, Windows saves *block* rules for `python.exe`
on Public networks, and these override the allow rule above. The symptom is that
the Pi prints `Connected to command centre at 192.168.2.1` but the console still
says there is no answer. Check for and remove them:

```
Get-NetFirewallRule -Direction Inbound -Action Block | Where-Object DisplayName -like "*python*" | Select DisplayName, Profile, Enabled
Get-NetFirewallRule -Direction Inbound -Action Block | Where-Object DisplayName -like "*python*" | Remove-NetFirewallRule
```

### 4. Check the link

In any terminal:

```
ipconfig
ping 192.168.2.2         # replies from the Pi
```

You can also log in to the Pi over the tether with `ssh pirov@192.168.2.2`.

Then run the console (see [Run the console](#4-run-the-console)), choose
**CONNECT VEHICLE**, and enter IP `192.168.2.2`, CMD port `5600`, telemetry
port `5601`, video port `5602` (or load the saved `DEMO` profile, which has
these values and the default reference values).

### Troubleshooting the link

| Symptom | Check |
|---|---|
| Adapter shows *Network cable unplugged* | Tether not seated, ROV not powered, or the Pi has not finished booting. |
| `ipconfig` shows `169.254.x.x` on the tether adapter | The static IP was not applied (still on automatic). Repeat step 2 on the correct adapter. |
| `ping 192.168.2.2` times out, adapter connected | Wrong adapter was given the IP, or the Pi's `rov-tether` profile is not active. On the Pi: `ip -4 addr show eth0` should show `192.168.2.2/24`; if not, `sudo nmcli con up rov-tether`. |
| Ping works, CONNECT times out, Pi prints nothing about a command centre | Wrong IP or port in the CONNECT dialog. |
| Ping works, Pi prints `Connected to command centre`, console still waits | Laptop firewall: most likely a `python.exe` block rule (step 3). |
| Telemetry works, no video | Firewall rule is missing UDP 5602, or another program (e.g. `ffplay`) is already listening on 5602. |
| Wi-Fi internet stops working while tethered | A default gateway was entered on the tether adapter. Clear it. |
| Video area says *PyAV not installed* | The venv was built before `av` was added. Re-run `python -m pip install -r py_requirements.txt`. |
| Video area says *UDP 5602 is in use by another program* | Close `ffplay`, VLC or anything else listening on the video port. |
| Event log never shows *Reference values applied by the Pi* | The Pi program is not replying with `ref_ack` (it may be an older version without reference-packet support). The console keeps resending every 1 s. |

---

## Operating the Console

### Controls (DualShock 3)

| Input | Action |
|---|---|
| Left stick | Forward/back (surge) and side to side (sway) |
| Right stick left/right | Rotate (yaw) |
| L2 (analog) | Descend |
| R2 (analog) | Ascend |
| D-pad up / down | Camera tilt, 5° per step, −45° to +45° (hold to repeat; armed only) |
| START, hold 1 s | ARM (or leak recovery, see below) |
| START, tap | DISARM when armed |
| SELECT or PS | E-STOP: disarm and zero all thrusters immediately |
| L1 / R1 | Thrust gain down / up (25 - 50 - 75 - 100 %; armed only) |
| CROSS, hold 5 s | Zero depth |
| CROSS, hold 1 s (while zeroed) | Clear the depth zero |
| TRIANGLE | Toggle all telemetry units SI ↔ imperial |
| SQUARE | Drop an operator mark in the event log |
| Keyboard SPACE | E-STOP (when the console window has focus) |

On an Xbox controller the same controls are on LT/RT, LB/RB, MENU (arm),
VIEW or XBOX (E-STOP), Y (units), X (mark) and A (zero depth).
Help > Dualshock3 Map / Xbox Map in the console shows both layouts.

> **Keyboard:** SPACE (E-STOP) is the only key that acts on the ROV. Anything
> else that controls the vehicle or sends something to it (arming, CONNECT,
> applying reference values, the demo leak toggle) is done with the controller
> or the mouse. The keyboard is only for typing values into the dialogs and for
> moving around the main menu.

### Arming

Hold START (or the on-screen ARM button) for 1 s. Arming is refused, with the
reason in the event log, unless:

- a controller is connected,
- both sticks are centred and L2/R2 are released, and
- telemetry is arriving from the Pi (`REQUIRE_LINK_TO_ARM` in `config.py`).

Disarming and E-STOP always work, with or without a controller.

While the ROV is **disarmed** (after E-STOP, a START tap, or any failsafe),
the camera tilt and thrust gain are locked at their current settings and the
sticks and triggers do nothing; pressing the D-pad or L1/R1 logs
`… locked — arm first`. Everything unlocks once the ROV is armed again.

### Failsafes

The console disarms automatically and logs a `FAIL` entry when:

- the controller disconnects,
- no telemetry arrives for 1 s (link lost), or
- a leak is reported.

When the controller disconnects, the console also sends a zero-thrust frame
straight away (like E-STOP), and the Controller status row shows a pulsing
**MISSING**. The camera tilt stays at its current angle. Once the controller
is plugged back in, arm as normal (hold START for 1 s); the ROV never re-arms
on its own.

On the ROV side, the Pi is expected to zero all thrusters if no valid command
packet arrives for about 250 ms (see the wire contract in `link.py`).

### Leak alarm and recovery

When the STM32 reports a leak, the console disarms, shows a pulsing **LEAK**
status, logs `LEAK DETECTED — surface the vehicle`, and locks the camera tilt
at its current angle. Surface the vehicle.

To recover, hold START (or the ARM button) for 1 s. The console sends a
*recover* request for 0.5 s. If the STM32 finds the leak sensor dry it clears
the leak shutdown and the console arms. If the shutdown is still set 1 s later,
the event log shows `Recover refused — leak sensor still wet`.

### Depth zero

Hold CROSS (or the ZERO chip on the depth card) for 5 s. Every depth reading
during the hold is averaged and that depth is shown as 0 m from then on;
releasing early cancels. Clear it by clicking REL or holding CROSS for 1 s.
This only changes the display; the Pi and STM32 still use true depth.

### Bar30 reference values

The depth calculation on the STM32 uses three reference values:

| Value | Default | Allowed range |
|---|---|---|
| Surface pressure | 1013.25 hPa (shown in hPa, kPa or mbar) | 800 - 1100 hPa |
| Water density | 1000 kg/m³ (fresh water; about 1025 kg/m³ for sea water) | 900 - 1100 kg/m³ |
| Second-order pressure calibration | ON (for water below 20 °C) | ON / OFF |

Set them in the CONNECT VEHICLE dialog (they are saved with the vehicle
profile) or during a session with File > Reference Values…. The console sends
them to the Pi and resends them every 1 s until the Pi confirms them; the event
log then shows `Reference values applied by the Pi`. If the Pi restarts, they
are sent again automatically.

### Demo mode

DEMO MODE runs the console against a simulated vehicle; nothing is sent over
the network and there is no camera.

- If no controller is plugged in, a simulated controller arms the vehicle and
  runs through the controls on a 40 s loop. Plugging in a real controller
  takes over immediately.
- The simulated link drops a short burst of command packets every 6 - 15 s,
  so the packet-loss display can be checked.
- Use **Demo > Toggle Simulated Leak** to make the simulated leak sensor wet
  or dry, to practise the leak alarm and recovery.

Both extras can be turned off with `DEMO_SIM_PAD` and `DEMO_PACKET_LOSS` in
`config.py`.

---

## Developer Reference

### Project layout

```
rov_console.py                  entry point: venv/version check, Ctrl+C handling, starts the app
command_center_py/
  app.py                        switches between the main menu and the console
  config.py                     tuning constants: network defaults, rates, deadzones, thruster mix
  profiles.py                   saved vehicle profiles (vehicle_profiles/*.json)
  reference.py                  Bar30 reference values: validation, units, profile storage
  gamepad.py                    DualShock 3 / Xbox input via SDL2 (pygame-ce), polled in its own thread
  demo_pad.py                   simulated controller for demo mode
  mixer.py                      stick shaping and thruster mixing (pure maths, no UI)
  link.py                       UDP command/reference packets out, JSON telemetry in, demo simulator
  video.py                      camera stream receiver (PyAV), decoded in its own thread
  ui/theme.py                   colours, fonts, label helper
  ui/widgets.py                 custom-painted gauges and composite widgets
  ui/reference_fields.py        reference-value inputs and the Reference Values dialog
  ui/start_window.py            main menu, CONNECT VEHICLE and CONTROLLER MAP dialogs
  ui/main_window.py             console window: layout, arming, failsafes, leak recovery, event log
  ui/assets/                    logo and icon (SVG)
vehicle_profiles/               one JSON file per saved vehicle (DEMO.json included)
UI_Design_Files/                HTML design mock-ups for the main menu and console
```

### Network protocol (summary)

The full wire contract, byte by byte, is in the docstring at the top of
`command_center_py/link.py`. The Pi side must match it.

| Message | Direction | Port | Format |
|---|---|---|---|
| Command | laptop → Pi | UDP 5600 | 16 bytes, magic `RV`, 50 Hz: armed/recover flags, sequence number, six thruster values (−100 to +100 %), camera tilt (°), CRC-16/CCITT-FALSE |
| Reference values | laptop → Pi | UDP 5600 | 16 bytes, magic `RF`: second-order flag, `ref_seq`, surface pressure (hPa, float32), water density (kg/m³, float32), CRC-16 |
| Telemetry | Pi → laptop | UDP 5601 | One JSON object per datagram, SI units, any key optional, `null` while a sensor is faulted |
| Video | Pi → laptop | UDP 5602 | H.264 in MPEG-TS |

Telemetry keys: `depth_m`, `pressure_kpa`, `water_c`, `internal_c`, `roll`,
`pitch`, `yaw`, `voltage`, `leak`, `faults`, `fault_flags`, `stm32`,
`uart_errors`, `ack` (last command sequence received), `rx_cmds` (total
commands received) and `ref_ack` (last `ref_seq` applied). `ack` and `rx_cmds`
are used for the round-trip time and packet-loss figures.

### Vehicle profile format

```json
{
  "name": "DEMO",
  "ip": "192.168.2.2",
  "cmd_port": 5600,
  "telem_port": 5601,
  "video_port": 5602,
  "surface_pressure_hpa": 1013.25,
  "surface_unit": "hPa",
  "water_density": 1000.0,
  "second_order": true
}
```

`video_port` and the reference values are optional; older profiles without
them use the defaults from `config.py`.

### Tuning

Bench settings live in `command_center_py/config.py`: stick deadzone and expo,
trigger deadzone, gain steps, camera tilt limits, hold times, link timeout,
reference-value defaults and the thruster mix table.

> **Important:** verify the thruster mix signs on the bench **with the
> propellers off**. Flip a coefficient's sign (or a whole row, for a reversed
> propeller) until each stick moves the ROV the right way.
