# Quick Guide: working on the program day to day

What to do each time you sit down to work on the Command Centre, or just want to
run it from the terminal. No ROV or tether is needed: everything below can be
tested in **DEMO MODE**.

If this is your first time on this laptop, start with the one-time
Developer Setup just below; otherwise skip to
[step 1](#1-open-a-terminal-in-the-repo).

---

## First time only: Developer Setup

The app runs on **Python 3.14** in a `.venv` in the repo's top directory. The
venv is not committed; build it from `py_requirements.txt`, which pins exact
versions. Get the repo first:

```
git clone https://github.com/Thomas1B/CamosunROV_CommandCentre.git
```

Then:

**A. Install Python 3.14** (once per laptop). It installs alongside other
versions. Recommended: install the Python install manager from python.org and run:

```
py install 3.14
```

(With the classic installer, untick "Add to PATH" if you don't want 3.14 as your
default `python`.) Then check it's there:

```
py -0
```

**B. Create the venv** (once, from the repo's top directory). Use `py -3.14`, not
`python`, which may pick another version:

```
py -3.14 -m venv .venv
```

**C. Activate and install:**

```
.venv\Scripts\activate
python --version                      # must print Python 3.14.x
python.exe -m pip install --upgrade pip
python -m pip install -r py_requirements.txt
```

If the version is wrong, delete `.venv` and repeat step B.

**D. Run:**

```
py rov_console.py
```

The program refuses to start outside the venv or on another Python version, and
says which step to repeat. From now on, use steps 1–8 below each time.

---

## 1. Open a terminal in the repo

## 2. Get the latest code

```
git pull
```

## 3. Activate the venv

```
.venv\Scripts\activate
```

`(.venv)` appears at the start of the prompt. Do this in every new terminal.

If PowerShell says *running scripts is disabled on this system*, run this once,
then activate again:

```
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 4. Update packages (only if `py_requirements.txt` changed)

If `git pull` listed `py_requirements.txt` among the changed files:

```
python -m pip install -r py_requirements.txt
```

It's safe to run any time; it only installs what's missing or out of date.

To add or upgrade a package yourself: pin the exact version in
`py_requirements.txt`, run the line above, test, and commit the file.

## 5. Run the program

```
py rov_console.py
```

## 6. Test without the ROV: DEMO MODE

On the main menu choose **DEMO MODE**, then **CONNECT**. The console opens on a
simulated vehicle after the countdown; nothing is sent over the network.

- With no controller plugged in, a simulated controller drives it on a loop.
  Plug in a controller and it takes over.
- **Demo > Reset Demo** starts over; **Demo > Toggle Simulated Leak** tests the
  leak alarm.
- Logs and profiles are saved in `C:\Users\Public\Documents\CamosunROV_Data`
  (**ABOUT → OPEN DATA FOLDER**).

## 7. Connect to the real ROV (tether setup)

Skip this if you're only using DEMO MODE. The network setup is needed once per
laptop; after that, just plug in the tether and connect.

The laptop and Pi form a two-device network over the Fathom tether with no
router or DHCP, so both use static IPs. Do this once per laptop; the Pi is
already configured by `setup_pi.sh` in CamosunROV_Pi (`rov-tether` profile).

| Device | IP address | Subnet mask | Receives on |
|---|---|---|---|
| Raspberry Pi (`eth0`) | `192.168.2.2` | `255.255.255.0` | UDP 5600 (commands) |
| Laptop | `192.168.2.1` | `255.255.255.0` | UDP 5601 (telemetry), 5602 (video) |

#### 7.1 Plug in the tether

Connect the tether and power the ROV. The port's link light comes on once the
Pi has booted.

> **Tip:** If you use the built-in Ethernet port for internet elsewhere, keep a
> USB-to-Ethernet adapter just for the tether. Each adapter keeps its own IP
> settings.

#### 7.2 Set a static IP

1. **Win + R** → `ncpa.cpl`.
2. Right-click the tether adapter (unplug the tether to see which one) →
   **Properties** → **Internet Protocol Version 4 (TCP/IPv4)** → **Properties**.
3. **Use the following IP address:** IP `192.168.2.1`, mask `255.255.255.0`.
   Leave the gateway and both DNS boxes **blank** (a gateway here would stop
   Wi-Fi internet). **OK** → **Close**.

To undo, choose **Obtain an IP address automatically**.

#### 7.3 Open the firewall

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

#### 7.4 Check the link

```
ipconfig
ping 192.168.2.2
```

`ssh pirov@192.168.2.2` also works over the tether. Then run the console,
choose **CONNECT VEHICLE** and enter IP `192.168.2.2`, ports `5600` / `5601` /
`5602` (or load the saved `ROV-01` profile, which has these and the default
reference values).

#### Troubleshooting

| Symptom | Check |
|---|---|
| *Network cable unplugged* | Tether not seated, ROV off, or Pi still booting. |
| `ipconfig` shows `169.254.x.x` | Static IP not applied; repeat 7.2 on the right adapter. |
| Ping times out, adapter connected | Wrong adapter configured, or Pi's `rov-tether` profile inactive. On the Pi, `ip -4 addr show eth0` should show `192.168.2.2/24`; if not, `sudo nmcli con up rov-tether`. |
| Ping works, CONNECT times out, Pi silent | Wrong IP or port in CONNECT. |
| Pi prints `Connected to command centre`, console still waits | Laptop firewall, most likely a `python.exe` block rule (7.3). |
| Telemetry but no video | Rule missing UDP 5602, or another program is on 5602. |
| *UDP 5602 is in use by another program* | Close `ffplay`, VLC or anything else on the video port. |
| *PyAV not installed* | Venv predates `av`; re-run `pip install -r py_requirements.txt`. |
| Wi-Fi internet stops while tethered | Clear the gateway on the tether adapter. |
| *Reference values applied by the Pi* never appears | Pi isn't replying with `ref_ack` (possibly an older version). The console resends every 1 s. |

## 8. Finish

Disarm, close the console, then **QUIT → QUIT** on the main menu (or Ctrl+C in
the terminal).
