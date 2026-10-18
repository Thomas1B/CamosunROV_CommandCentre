# CamosunROV Command Centre

Pilot command centre for the Camosun capstone underwater ROV.

> **Note:** We plan to release the command centre as a Windows executable
> (`.exe`) that runs without installing Python. Until then, set it up and run it
> by following [Tether Network Setup](#tether-network-setup) and
> [Developer Setup](#developer-setup).

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
  The port needs a static IP address. See [Tether Network Setup](#tether-network-setup).

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

---

## Tether Network Setup

The laptop and the ROV's Raspberry Pi talk over the Fathom tether as a small
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
port `5601` (or load the saved `DEMO` profile, which has these values).

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
