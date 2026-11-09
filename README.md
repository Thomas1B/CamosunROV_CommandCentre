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
level, the leak sensor, why the STM32 last reset, and link quality (round-trip
time and packet loss).

Main features:

- Arm/disarm and an emergency stop (controller, keyboard SPACE, or the Vehicle menu)
- Adjustable thrust gain (25 / 50 / 75 / 100 %)
- Live camera view (H.264 over UDP, decoded with PyAV) with a HUD; shows
  *VIDEO LOST* over the last frame if the stream stops for 1.5 s
- Camera recording (REC button) to `recordings/*.mkv`, full quality, almost no CPU
- Failsafes: the ROV is automatically disarmed if the controller disconnects,
  the tether link is lost, or a leak is detected
- No keyboard control of the ROV except SPACE for E-STOP
- Leak alarm with recovery: after a leak the thrusters are disarmed and the
  camera tilt is locked until the STM32 confirms the leak sensor is dry
- Depth zero: take the current depth as 0 m (display only) and clear it again
- Bar30 depth sensor reference values (surface pressure, water density,
  second-order calibration), sent to the Pi/STM32 and confirmed by it
- Event log with operator marks
- Main menu: connect to a vehicle (with saved vehicle profiles), demo mode, controller maps,
  controller profiles (stick drift / deadzone / range calibration), saved session logs
- Demo mode with a simulated vehicle, a simulated controller and simulated
  packet loss, for testing without the ROV

---

## Program Requirements

### Computer

- Windows 10 or 11 (64-bit)
- An Ethernet (RJ45) port for the ROV tether. A USB-to-Ethernet adapter also works.
  The port needs a static IP address. See [Tether Network Setup](#tether-network-setup).

> **Note:** The command centre was built for Windows and has not been tested on
> macOS or Linux.

### Controller

One of:

- Xbox controller. Windows has the driver built in.
- PlayStation DualShock 3 controller, connected by USB cable
  - **DsHidMini driver:** Windows has no built-in driver for the DualShock 3, so
    download and install DsHidMini from
    [docs.nefarius.at/Downloads](https://docs.nefarius.at/Downloads/) before
    plugging in the controller.

Switch the on-screen button names to match with the DUALSHOCK 3 / XBOX toggle
above STICK INPUT in the console.

Worn sticks drift. Calibrate each controller once in **CONTROLLER PROFILES**
(see [Controller profiles](#controller-profiles)).

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
python.exe -m pip install --upgrade pip
python -m pip install -r py_requirements.txt
```

#### 4. Run the console

```
py rov_console.py
```

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

### Controls

| Xbox | DualShock 3 | Action |
|---|---|---|
| Left stick | Left stick | Forward/back (surge) and side to side (sway) |
| Right stick left/right | Right stick left/right | Rotate (yaw) |
| LT (analog) | L2 (analog) | Descend |
| RT (analog) | R2 (analog) | Ascend |
| D-pad up / down | D-pad up / down | Camera tilt, 5° per step, −45° to +45° (hold to repeat) |
| MENU, hold 1 s | START, hold 1 s | ARM (or leak recovery, see below) |
| MENU, tap | START, tap | DISARM when armed |
| VIEW | SELECT | E-STOP: disarm and zero all thrusters immediately |
| LB / RB | L1 / R1 | Thrust gain down / up (25 - 50 - 75 - 100 %) |
| A, hold 5 s | CROSS, hold 5 s | Zero depth |
| A, hold 1 s (while zeroed) | CROSS, hold 1 s (while zeroed) | Clear the depth zero |
| Y | TRIANGLE | Toggle all telemetry units SI ↔ imperial |
| X | SQUARE | Drop an operator mark in the event log (hold to repeat, one per second) |
| Keyboard SPACE | Keyboard SPACE | E-STOP (when the console window has focus) |

Help > Dualshock3 Map / Xbox Map in the console shows both layouts.

> **Keyboard:** SPACE (E-STOP) is the only key that acts on the ROV. Anything
> else that controls the vehicle or sends something to it (arming, CONNECT,
> applying reference values, the demo leak toggle) is done with the controller
> or the mouse. The keyboard is only for typing values into the dialogs and for
> moving around the main menu.
>
> **The controller only works in the console** (main window, demo mode
> included). The main menu and its cards (CONNECT VEHICLE, VIEW LOGS, VIEW
> RECORDINGS, CONTROLLER MAP, ...) use the mouse and keyboard only. The one
> exception is CONTROLLER PROFILES, which reads the sticks and triggers to
> calibrate them; its buttons still don't operate the page.

### Controller profiles

Without a profile, every controller uses the defaults in `config.py`: a 0.20
stick deadzone and a 0.06 trigger deadzone, with no correction for an
off-centre stick or for sticks that don't reach full travel. A **controller
profile** measures this per controller, so a drifting stick reads exactly 0 at
rest and full throw reads exactly ±100 %.

**Making one.** In the main menu, open **CONTROLLER PROFILES** with the
controller plugged in, press **NEW** (or pick a profile to redo it), then
**CALIBRATE**:

Press **OK** once your hands are off the controller, then:

1. **LEFT STICK**
   - **1a FLICK (×12):** the page shows an arrow (→ ↗ ↑ …, a new random
     direction each time). Push the stick to the edge that way and **let go**.
     Once it has settled, the page records where it stopped (amber dot). Stick
     springs don't return to exactly the same spot every time. The settled
     position depends on which way the stick came back from. So the **centre**
     is the average of the 12 settled points, and the **deadzone** covers the
     furthest one plus the stick's jitter (at least 0.03). However the spring
     leaves the stick, it reads 0.
   - **1b:** push it to the edge and turn it clockwise ↻ 10 times.
   - **1c:** turn it counter-clockwise ↺ 10 times.
2. **RIGHT STICK:** the same: **2a** flicks, **2b** clockwise, **2c**
   counter-clockwise.

   The turns measure each axis's real **min** / **max**. The page counts flicks
   and turns ("4 / 12 flicks", "4 / 10 turns") and moves on by itself when a
   part is done. A flick only counts when it goes past 70 % of the travel within
   45° of the arrow. A turn only counts while the stick is pushed out past half
   its travel, and turning the wrong way takes turns back off (never below 0).
   **NEXT** skips the rest of a part.
3. **TRIGGERS:** press L2 and R2 (LT / RT) all the way, release, then press
   **FINISH**. This measures each trigger's **max**. Their **rest** and jitter
   are measured while the sticks settle during the flicks, when the triggers
   aren't being touched.

The live view shows the raw stick (white dot), the profile's range (dashed teal
box) and its deadzone (amber box). Under the trigger bars, **OUTPUT** shows the
values the console will use: 0.00 at rest and ±1.00 at full throw. Every value
can be edited by hand. Give the profile a name and **SAVE** it. It's written to
`controller_profiles/<name>.json`.

If a stick got fewer than 3 flicks, barely moved, or a trigger wasn't pressed
fully, the page says so and keeps the old values for it. The controller's buttons don't operate this
page, because you're using it to calibrate; use the mouse and keyboard. Esc or
CLOSE closes it, and asks first if there are unsaved changes.

**Which profile is used.** You choose it each time in **CONNECT VEHICLE**,
with the **CONTROLLER PROFILE** setting (below SECOND-ORDER PRESSURE CAL):

- **Defaults (no calibration)**, selected every time the dialog opens: the
  `config.py` defaults.
- A saved profile: that profile, whichever controller is plugged in.

Nothing is picked automatically. Each profile also notes which controller it
was made for (**USE CONNECTED**, or filled in when you calibrate). That note is
only a reminder in the profile list. Demo mode always uses the defaults. When
the controller connects, the console's event log says which profile it's using,
e.g. `PAD Controller profile "Josh DS3"`. The dashed deadzone ring on the
console's stick views follows the profile.

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

### STM32 reset reason

The **STM32 last reset** row in SYSTEM STATUS shows why the STM32 last
restarted, as reported in every telemetry packet: `POWER-ON` (power-up or a
battery brown-out), `PIN` (reset button or debugger), `SOFTWARE`, `OTHER`, or
`WATCHDOG`. Each time the STM32 (re)connects the event log records it once.
`WATCHDOG` is shown in amber and logged as a warning: the STM32 firmware hung
for about 0.5 s and its watchdog (IWDG) restarted it. It is information, not a
fault, so the console does not disarm for it.

### Event log file and operator marks

Everything in the EVENT LOG is also saved to a CSV file in the `logs/` folder
(next to `vehicle_profiles/`), one file per console session, named by the
vehicle and then the local start time, e.g. `logs/DEMO_2026-10-31_23-44-18.csv`.
(Files saved by older versions start with the time instead,
`2026-10-31_23-44-18_DEMO.csv`; VIEW LOGS and VIEW RECORDINGS still read them.)
Exports and saved video frames are named after the file, so they start with the
vehicle too.
The first log line on screen shows the file name. Each row is written to disk
immediately, so the file is complete even after a crash. The folder is
git-ignored.

| Column | Contents |
|---|---|
| `local_time` | Laptop local time, `YYYY-MM-DD HH:MM:SS.mmm` |
| `utc_offset` | Local time minus UTC, e.g. `-07:00` |
| `utc_time` | Same moment in UTC |
| `tag`, `message` | As shown on screen (`SYS`, `LINK`, `MARK`, ...) |
| `depth_m`, `rel_depth_m`, `pressure_kpa`, `water_temp_c`, `internal_temp_c`, `roll_deg`, `pitch_deg`, `yaw_deg`, `heading_deg`, `heading_cardinal`, `battery_v`, `leak` | Telemetry snapshot, `MARK` rows only |
| `video_time`, `video_file` | Position in the camera recording (`mm:ss`) and its file name, `MARK` rows made while recording |

An operator mark (SQUARE / X; hold to repeat once per second) records depth,
zeroed depth (if a zero is set), pressure, water and internal temperature,
roll, pitch, yaw (−180° to +180°), heading (0–360° and compass point, e.g.
`SW`), battery voltage and leak status (`DRY`, `LEAK` or `NO DATA`). The
on-screen line shows the same values; a value that is unavailable (sensor
faulted or link down) shows as `--` on screen and is left empty in the file.

**Leaving the console.** When you exit the console (it must be disarmed), it
sends its last zero-thrust frames and closes the link.

If you used **● REC** in the session, the **SAVE RECORDING?** pop-up comes
first. It lists each recording made in the session with a tick box (all ticked
to start). You must pick one; Esc does nothing:

- **YES, SAVE**: keep the ticked recordings and delete any you unticked. The
  event log is saved in `logs/` automatically and the console closes; the
  SESSION LOG pop-up is skipped. Greyed out while nothing is ticked.
- **NO, DELETE**: delete all of the session's recordings (click twice to
  confirm), then go on to the SESSION LOG pop-up.

The event log records each recording kept or deleted. Sessions without a
recording go straight to the **SESSION LOG** pop-up. The pop-up previews the log in two tabs: *Operator
marks* (one column per value) and *All events*. You must pick one of three
options; Esc does nothing:

- **SAVE**: keep the session file in `logs/` and exit.
- **EXPORT…**: save a copy as Excel (`.xlsx`, with *Marks* and *Events*
  sheets), CSV (`.csv`) or PDF (`.pdf`, A4 landscape) wherever you choose. The
  pop-up stays open, so you can export more than one format before choosing
  SAVE or DISCARD.
- **DISCARD**: delete the session file from `logs/` and exit. Click it twice to
  confirm. Copies you already exported are not touched.

Both pop-ups are skipped when the program is stopped with Ctrl+C; the
recordings and the log are kept. Excel export needs `openpyxl`, which is in `py_requirements.txt`. If
your venv is older, re-run `python -m pip install -r py_requirements.txt`.

**Viewing saved logs.** In the main menu, **VIEW LOGS** opens the **SESSION LOGS**
card. It lists every session in `logs/`, newest first, with its start time, vehicle,
number of events and marks. Pick one (mouse or arrow keys) to see the same
*Operator marks* and *All events* tables as the exit pop-up, plus the session
length and its UTC times. **EXPORT…** saves it as `.xlsx`, `.csv` or `.pdf`.
**DELETE** removes the file (click twice). **OPEN FOLDER** opens `logs/` in File
Explorer. Drag the grip in the card's bottom-right corner to resize it (it keeps that
size until the program closes). Esc, ○ / B, ✕ or CLOSE close the card.

### Recording the camera

Click **● REC** in the console toolbar to record the camera stream; click it again
(**■ REC 02:14**) to stop. Recordings are saved in the `recordings/` folder,
one file per recording, named like the logs, e.g.
`recordings/ROV-01_2026-11-01_18-40-05.mkv`. The folder is git-ignored. There's
no controller button for it; use the mouse.

- **Full quality, almost no CPU.** The H.264 video the Pi sends is saved exactly
  as received. It isn't decoded or compressed again. At the Pi's 4 Mbit/s that's
  about 30 MB per minute (1.8 GB per hour).
- **Starts cleanly.** Recording starts at the next key frame, at most 0.5 s after
  the click, so the file never opens on a broken picture. The button shows
  **● REC …** until then.
- **Dropouts.** If the stream drops out (the button shows ⏸ and the log says
  *Camera stream lost*), the same file continues when the video comes back. The
  gap is left out, so the time shown is the length of video in the file.
- **Crash-safe.** If the program or laptop crashes while recording, everything up
  to about the last second is kept.
- **Event log.** The event log records *Recording started* and *Recording
  stopped* (with length, size and file name). An operator mark made while
  recording ends with the video time, e.g. `· REC 02:14`. Every event logged
  while recording gets the `video_time` and `video_file` columns in the log file,
  which VIEW RECORDINGS uses to put the events on the video.
- **Closing the console** stops the recording and asks whether to keep it
  (SAVE RECORDING?, see *Leaving the console*). Demo mode has no camera, so REC
  does nothing there.

The `.mkv` files play in VLC or the Windows Media Player / Films & TV app.
Packets lost on the tether show as a brief glitch, the same as on screen.

### Viewing recordings

**VIEW RECORDINGS** on the main menu (under VIEW LOGS) lists every
`recordings/*.mkv`, newest first, with start time, vehicle, length, size and how
many events (and operator marks) were logged while it was recording. It plays them with a
built-in player, so nothing extra has to be installed.

- **Play.** ▶ PLAY / ⏸ PAUSE, ◀◀ 3 s / 3 s ▶▶, ◀ 1 s / 1 s ▶, and a seek bar. Click anywhere
  on the bar to jump there, or drag the handle.
- **Events.** The EVENTS list shows every event-log line from while that file was
  recording (link, alarms, arming, warnings, operator marks, ...) with its video
  time, local time and tag. Operator marks show depth, heading, water temperature
  and leak. Click an event to jump to it. Events are read from the `video_time` /
  `video_file` columns in `logs/*.csv`, so a deleted log takes its events with it.
  Recordings made before this update only have their operator marks.
- **OPEN FOLDER** opens `recordings/` in File Explorer.
- **SAVE FRAME…** pauses and saves the frame on screen as a PNG (default folder
  `Pictures`, named after the recording and the video time).
- **EXPORT…** opens a Save dialog (default folder `Videos`); the *Save as type*
  picks what is saved:
  - **MP4 video**: the recording as an `.mp4` that plays anywhere (phones,
    PowerPoint, Teams, browsers). The video is copied, not re-encoded, so it
    takes seconds and keeps full quality. Progress shows in the footer, and
    you can keep using the player meanwhile.
  - **Events — Excel / CSV**: the EVENTS IN THIS RECORDING list, with the
    video time first, then the same columns as the session-log export (Excel
    gets *Marks* and *Events* sheets).
- **DELETE** deletes the selected file. Click it twice; the first click arms it
  for 4 s. This can't be undone.
- **Keys.** Space play/pause, ← / → 3 s, Shift+← / → 1 s, ↑ / ↓ pick a
  recording, Esc close.

The window can be resized from the bottom-right corner.

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
