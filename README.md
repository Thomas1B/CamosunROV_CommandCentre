# CamosunROV Command Centre

Pilot command centre for the Camosun capstone underwater ROV: a Windows desktop
app that reads a game controller (DualShock 3 or Xbox), mixes the inputs into
commands for the ROV's six thrusters and camera tilt servo, and sends them over
the tether to the Raspberry Pi, which forwards them to the STM32 motor
controller.

It displays the Pi's live camera and telemetry: depth, pressure, water and
internal temperature, roll/pitch/heading, battery voltage and estimated charge,
leak sensor, STM32 reset reason, and link quality (round-trip time, packet loss).

## Quick Start (Windows, no Python needed)

Download `CamosunROV.zip` from the
[v1.0.0 release](https://github.com/Thomas1B/CamosunROV_CommandCentre/releases/tag/v1.0.0)
and follow the instructions there. Then set up the tether once:
[Tether Network Setup](#tether-network-setup).

To run from source instead, see [Developer Setup](#developer-setup).

Features:

- Arm/disarm and E-STOP (controller, keyboard SPACE, or Vehicle menu)
- Thrust gain 25 / 50 / 75 / 100 %
- Live H.264 video (PyAV) with HUD; *VIDEO LOST* after 1.5 s without frames
- Camera recording to `recordings/*.mkv` at full quality with almost no CPU
- Failsafe disarm on controller loss, link loss or leak
- Leak recovery: thrusters disarmed and tilt locked until the STM32 reports dry
- Display-only depth zero
- Bar30 reference values sent to and confirmed by the Pi/STM32
- Event log with operator marks
- Main menu: vehicle profiles, demo mode, controller maps, controller profiles
  (drift/deadzone/range calibration), saved session logs and recordings
- Demo mode with simulated vehicle, controller and packet loss

---

## Requirements

- **Windows 10 or 11 (64-bit).** Not tested on macOS or Linux.
- **Ethernet port** (or USB-to-Ethernet adapter) with a static IP — see
  [Tether Network Setup](#tether-network-setup).
- **Controller:**
  - Xbox: driver built into Windows.
  - DualShock 3 (USB): install the
    [DsHidMini driver](https://docs.nefarius.at/Downloads/) before plugging in.

  Match the on-screen button names with the DUALSHOCK 3 / XBOX toggle above
  STICK INPUT. Calibrate each controller once in
  [Controller profiles](#controller-profiles) to remove stick drift.
- **Python 3.14** in the project venv, only when running from source — see
  below.

---

## Developer Setup

The app runs on **Python 3.14** in a `.venv` in the repo's top directory. The
venv is not committed; build it from `py_requirements.txt`, which pins exact
versions.

1. **Install Python 3.14** (once). It installs alongside other versions.
   Recommended: install the Python install manager from python.org and run
   `py install 3.14`. (With the classic installer, untick "Add to PATH" if you
   don't want 3.14 as your default `python`.) Check with `py -0`.

2. **Create the venv** (once, from the repo's top directory). Use `py -3.14`,
   not `python`, which may pick another version:

   ```
   py -3.14 -m venv .venv
   ```

3. **Activate and install:**

   ```
   .venv\Scripts\activate
   python --version                      # must print Python 3.14.x
   python.exe -m pip install --upgrade pip
   python -m pip install -r py_requirements.txt
   ```

   If the version is wrong, delete `.venv` and repeat step 2.

4. **Run:**

   ```
   py rov_console.py
   ```

   The program refuses to start outside the venv or on another Python version,
   and says which step to repeat.

**Day-to-day:** activate the venv in each new terminal. After pulling, re-run
the `pip install -r` line if `py_requirements.txt` changed. If something
breaks, delete `.venv` and repeat steps 2–3. To add or upgrade a package, pin
the exact version in `py_requirements.txt`, install, test and commit it.

---

## Tether Network Setup

The laptop and Pi form a two-device network over the Fathom tether with no
router or DHCP, so both use static IPs. Do this once per laptop; the Pi is
already configured by `setup_pi.sh` in CamosunROV_Pi (`rov-tether` profile).

| Device | IP address | Subnet mask | Receives on |
|---|---|---|---|
| Raspberry Pi (`eth0`) | `192.168.2.2` | `255.255.255.0` | UDP 5600 (commands) |
| Laptop | `192.168.2.1` | `255.255.255.0` | UDP 5601 (telemetry), 5602 (video) |

### 1. Plug in the tether

Connect the tether and power the ROV. The port's link light comes on once the
Pi has booted.

> **Tip:** If you use the built-in Ethernet port for internet elsewhere, keep a
> USB-to-Ethernet adapter just for the tether. Each adapter keeps its own IP
> settings.

### 2. Set a static IP

1. **Win + R** → `ncpa.cpl`.
2. Right-click the tether adapter (unplug the tether to see which one) →
   **Properties** → **Internet Protocol Version 4 (TCP/IPv4)** → **Properties**.
3. **Use the following IP address:** IP `192.168.2.1`, mask `255.255.255.0`.
   Leave the gateway and both DNS boxes **blank** (a gateway here would stop
   Wi-Fi internet). **OK** → **Close**.

To undo, choose **Obtain an IP address automatically**.

### 3. Open the firewall

Windows puts the cable link in the **Public** profile, which blocks incoming
UDP. In an **Administrator** PowerShell:

```
New-NetFirewallRule -DisplayName "CamosunROV UDP in" -Direction Inbound -Protocol UDP -LocalPort 5601,5602 -Action Allow -Profile Any
```

`-Profile Any` is required; a Private-only rule won't cover the tether.

If the Windows "Allow access?" pop-up for Python was ever closed or missed,
Windows saved **block** rules for `python.exe` that override the rule above
(symptom: the Pi prints `Connected to command centre at 192.168.2.1` but the
console gets no answer). List and remove them (for the `.exe`, replace
`*python*` with `*CamosunROV*`):

```
Get-NetFirewallRule -Direction Inbound -Action Block | Where-Object DisplayName -like "*python*" | Select DisplayName, Profile, Enabled
Get-NetFirewallRule -Direction Inbound -Action Block | Where-Object DisplayName -like "*python*" | Remove-NetFirewallRule
```

### 4. Check the link

```
ipconfig
ping 192.168.2.2
```

`ssh pirov@192.168.2.2` also works over the tether. Then run the console,
choose **CONNECT VEHICLE** and enter IP `192.168.2.2`, ports `5600` / `5601` /
`5602` (or load the saved `DEMO` profile, which has these and the default
reference values).

### Troubleshooting

| Symptom | Check |
|---|---|
| *Network cable unplugged* | Tether not seated, ROV off, or Pi still booting. |
| `ipconfig` shows `169.254.x.x` | Static IP not applied; repeat step 2 on the right adapter. |
| Ping times out, adapter connected | Wrong adapter configured, or Pi's `rov-tether` profile inactive. On the Pi, `ip -4 addr show eth0` should show `192.168.2.2/24`; if not, `sudo nmcli con up rov-tether`. |
| Ping works, CONNECT times out, Pi silent | Wrong IP or port in CONNECT. |
| Pi prints `Connected to command centre`, console still waits | Laptop firewall, most likely a `python.exe` block rule (step 3). |
| Telemetry but no video | Rule missing UDP 5602, or another program is on 5602. |
| *UDP 5602 is in use by another program* | Close `ffplay`, VLC or anything else on the video port. |
| *PyAV not installed* | Venv predates `av`; re-run `pip install -r py_requirements.txt`. |
| Wi-Fi internet stops while tethered | Clear the gateway on the tether adapter. |
| *Reference values applied by the Pi* never appears | Pi isn't replying with `ref_ack` (possibly an older version). The console resends every 1 s. |

---

## Operating the Console

### Controls

| Xbox | DualShock 3 | Action |
|---|---|---|
| Left stick | Left stick | Surge and sway |
| Right stick left/right | Right stick left/right | Yaw |
| LT / RT (analog) | L2 / R2 (analog) | Descend / ascend |
| D-pad up / down | D-pad up / down | Camera tilt, 5° steps, −45° to +45° (hold to repeat) |
| MENU, hold 1 s | START, hold 1 s | ARM (or leak recovery) |
| MENU, tap | START, tap | DISARM |
| VIEW | SELECT | E-STOP: disarm and zero thrusters |
| LB / RB | L1 / R1 | Thrust gain down / up |
| A, hold 5 s | CROSS, hold 5 s | Zero depth |
| A, hold 1 s (zeroed) | CROSS, hold 1 s (zeroed) | Clear depth zero |
| Y | TRIANGLE | Toggle SI / imperial units |
| X | SQUARE | Operator mark (hold: one per second) |
| SPACE | SPACE | E-STOP (console window focused) |

Help > Dualshock3 Map / Xbox Map shows both layouts.

> **Keyboard:** SPACE is the only key that acts on the ROV. Arming, CONNECT,
> reference values and the demo leak toggle use the controller or mouse; the
> keyboard is only for typing in dialogs and navigating the main menu.
>
> **The controller only works in the console** (including demo mode). Main
> menu cards use mouse and keyboard; CONTROLLER PROFILES reads the sticks and
> triggers for calibration but its buttons still don't operate the page.

### Controller profiles

Without a profile, controllers use the `config.py` defaults: 0.20 stick and
0.06 trigger deadzone, with no correction for off-centre or short-travel
sticks. A profile measures each controller so a drifting stick reads exactly 0
at rest and ±100 % at full throw.

**Creating one:** in **CONTROLLER PROFILES**, with the controller plugged in,
press **NEW** (or select a profile to redo), then **CALIBRATE**. Press **OK**
with your hands off the controller, then:

1. **Left stick**
   - **Flick ×20:** push to the edge in the direction of the arrow and let go.
     The first 8 flicks cover all 8 directions (each appears 2–3 times in
     total). Each settled position is recorded (amber dot). Because springs
     settle differently depending on return direction, the **centre** is the
     average of the 20 points and the **deadzone** covers the furthest one plus
     jitter (minimum 0.03).
   - **Clockwise ×10**, then **counter-clockwise ×10**, at the edge.
2. **Right stick:** same as left. The turns measure each axis's real
   **min/max**.
3. **Triggers:** press L2 and R2 (LT/RT) fully, release, then **FINISH**. This
   measures **max**; rest and jitter were measured during the flicks.

### Arming

Hold START (or the ARM button) for 1 s. Arming is refused, with the reason
logged, unless a controller is connected, both sticks are centred and L2/R2
released, and telemetry is arriving (`REQUIRE_LINK_TO_ARM` in `config.py`).
Disarm and E-STOP always work.

While disarmed, sticks and triggers do nothing and camera tilt and thrust gain
are locked; D-pad or L1/R1 logs `… locked — arm first`.

### Failsafes

The console disarms and logs `FAIL` when the controller disconnects, no
telemetry arrives for 1 s, or a leak is reported.

On controller disconnect it also sends a zero-thrust frame immediately and
shows a pulsing **MISSING**; tilt holds its angle. After reconnecting, arm as
normal — it never re-arms on its own.

The Pi is expected to zero all thrusters if no valid command arrives for about
250 ms (see the wire contract in `command_center_py/vehicle/link.py`).

### Leak alarm and recovery

On a leak report the console disarms, shows a pulsing **LEAK**, logs
`LEAK DETECTED — surface the vehicle` and locks camera tilt. Surface the
vehicle.

To recover, hold START (or ARM) for 1 s. The console sends a *recover* request
for 0.5 s; if the sensor is dry the STM32 clears the shutdown and the console
arms. If it's still set 1 s later, the log shows
`Recover refused — leak sensor still wet`.

### STM32 reset reason

**STM32 last reset** in SYSTEM STATUS shows `POWER-ON` (power-up or battery
brown-out), `PIN` (reset button or debugger), `SOFTWARE`, `OTHER` or
`WATCHDOG`, logged once per (re)connect. `WATCHDOG` (firmware hung ~0.5 s and
the IWDG restarted it) is shown in amber and logged as a warning, but does not
disarm.

### Event log and operator marks

Each session's event log is also written to `logs/<vehicle>_<local start
time>.csv` (e.g. `logs/DEMO_2026-10-31_23-44-18.csv`; git-ignored). The first
on-screen line shows the file name. Rows are written immediately, so the file
survives a crash. Exports and saved frames reuse the name.

| Column | Contents |
|---|---|
| `local_time` | `YYYY-MM-DD HH:MM:SS.mmm` |
| `utc_offset`, `utc_time` | e.g. `-07:00`, and the same moment in UTC |
| `tag`, `message` | As on screen (`SYS`, `LINK`, `MARK`, ...) |
| `depth_m`, `rel_depth_m`, `pressure_kpa`, `water_temp_c`, `internal_temp_c`, `roll_deg`, `pitch_deg`, `yaw_deg`, `heading_deg`, `heading_cardinal`, `battery_v`, `leak` | Telemetry snapshot (`MARK` rows only) |
| `video_time`, `video_file` | Recording position (`mm:ss`) and file, for events logged while recording |

An operator mark (SQUARE / X) records depth, zeroed depth (if set), pressure,
temperatures, roll, pitch, yaw (±180°), heading (0–360° and compass point,
e.g. `SW`), battery voltage and leak (`DRY`, `LEAK` or `NO DATA`).
Unavailable values show `--` on screen and are blank in the file.

### Leaving the console

Exit only while disarmed; the console sends final zero-thrust frames and closes
the link. Neither pop-up below can be skipped with Esc. Both are skipped on
Ctrl+C, which keeps recordings and the log.

**SAVE RECORDING?** (only if REC was used) lists the session's recordings, all
ticked:

- **YES, SAVE:** keep ticked recordings, delete unticked ones, save the log
  and exit (skips SESSION LOG). Disabled when nothing is ticked.
- **NO, DELETE:** delete all session recordings (click twice), then go to
  SESSION LOG.

**SESSION LOG** previews *Operator marks* and *All events*:

- **SAVE:** keep the log and exit.
- **EXPORT…:** save a copy as `.xlsx` (*Marks* and *Events* sheets), `.csv` or
  `.pdf` (A4 landscape). Stays open for further exports. Excel needs
  `openpyxl`; re-run `pip install -r py_requirements.txt` on older venvs.
- **DISCARD:** delete the log (click twice) and exit. Exported copies are kept.

The event log records each recording kept or deleted.

### Viewing saved logs

**VIEW LOGS** lists sessions in `logs/`, newest first, with start time,
vehicle, event and mark counts. Selecting one (mouse or arrow keys) shows the
same two tables plus session length and UTC times. **EXPORT…** (`.xlsx`,
`.csv`, `.pdf`), **DELETE** (click twice) and **OPEN FOLDER** are available.
The card can be resized from the bottom-right grip or maximised (button or
double-click the title bar). Esc, the close button or CLOSE exits.

### Recording the camera

Click **REC** in the toolbar to start; click again (it shows e.g. **REC
02:14**) to stop. Files go to `recordings/<vehicle>_<start time>.mkv`
(git-ignored). Mouse only; no controller button.

- **Full quality:** the Pi's H.264 stream is saved as received, not
  re-encoded — about 30 MB/min (1.8 GB/h) at 4 Mbit/s.
- **Clean start:** begins at the next key frame, within 0.5 s (button shows
  **REC …** until then).
- **Dropouts:** recording pauses when the stream drops (*Camera stream lost*)
  and resumes in the same file; gaps are omitted, so the timer shows video
  length.
- **Crash-safe:** everything up to about the last second is kept.
- **Logging:** *Recording started/stopped* (with length, size, file) are
  logged. Marks made while recording end with the video time (e.g.
  `· REC 02:14`), and all events get `video_time`/`video_file`.
- **On exit:** recording stops and SAVE RECORDING? appears. Demo mode has no
  camera, so REC does nothing.

Files play in VLC or Windows Media Player / Films & TV. Tether packet loss
shows as a brief glitch, as it does live.

### Viewing recordings

**VIEW RECORDINGS** lists `recordings/*.mkv`, newest first, with start time,
vehicle, length, size and event/mark counts, and plays them in a built-in
player.

- **Playback:** play/pause, ±3 s, ±1 s, and a seek bar (click or drag).
- **Events:** every log line from the recording, with video time, local time
  and tag (marks also show depth, heading, water temperature and leak). Click
  to jump there. Events come from `logs/*.csv`, so deleting a log removes its
  events.
- **SAVE FRAME…:** pauses and saves the current frame as PNG (default
  `Pictures`).
- **EXPORT…** (default `Videos`): **MP4 video** (copied without re-encoding;
  takes seconds, plays anywhere; progress in the footer), or **Events — Excel /
  CSV** (video time first, then the session-log columns).
- **DELETE:** click twice within 4 s. Cannot be undone.
- **OPEN FOLDER:** opens `recordings/`.
- **Keys:** Space play/pause, ←/→ 3 s, Shift+←/→ 1 s, ↑/↓ select recording,
  Esc close.

Resize or maximise the window as with VIEW LOGS.

### Depth zero

Hold CROSS (or the ZERO chip on the depth card) for 5 s; the depth averaged
over the hold becomes 0 m. Releasing early cancels. Clear it by clicking REL or
holding CROSS for 1 s. Display only — the Pi and STM32 use true depth.

### Bar30 reference values

| Value | Default | Range |
|---|---|---|
| Surface pressure | 1013.25 hPa (shown in hPa, kPa or mbar) | 800–1100 hPa |
| Water density | 1000 kg/m³ fresh (~1025 kg/m³ sea) | 900–1100 kg/m³ |
| Second-order pressure calibration | ON (for water below 20 °C) | ON / OFF |

Set them in CONNECT VEHICLE (saved with the vehicle profile) or via File >
Reference Values…. The console resends every 1 s until the Pi confirms
(`Reference values applied by the Pi`) and resends automatically if the Pi
restarts.

### Demo mode

Runs against a simulated vehicle; nothing is sent over the network and there is
no camera.

- With no controller plugged in, a simulated controller arms and runs through
  the controls on a 40 s loop. A real controller takes over immediately.
- The simulated link drops a burst of command packets every 6–15 s to exercise
  the packet-loss display.
- **Demo > Toggle Simulated Leak** toggles the leak sensor to practise
  recovery.

Disable the simulated controller or packet loss with `DEMO_SIM_PAD` and
`DEMO_PACKET_LOSS` in `config.py`.