r"""
Camosun ROV - topside control console
PySide6 UI + DualShock 3 input (SDL2 via pygame)

Control chain:  DualShock 3 -> this laptop (Windows) -> UDP -> Raspberry Pi -> STM32 -> thrusters

Run (Python 3.14, inside the repo's .venv - see README for first-time setup):
    .venv\Scripts\activate                        # once per terminal
    python rov_console.py --demo                  # no vehicle needed, simulated telemetry
    python rov_console.py --host 192.168.2.2      # real vehicle
    python rov_console.py --cmd-port 5600         # UDP port the Pi listens on for commands (default 5600)
    python rov_console.py --telem-port 5601       # UDP port this console listens on for telemetry (default 5601)
    python rov_console.py --help                  # list all options
    (running with no options at all is an error - pick --demo or --host)

-----------------------------------------------------------------------------
DUALSHOCK 3 CONTROLS
    Left stick ........ forward/back (surge) + side to side (sway)
    Right stick L/R ... rotate / turn (yaw)
    L2 (analog) ....... descend   (push deeper)
    R2 (analog) ....... ascend    (push up)
    D-pad up / down ... camera tilt servo (hold to repeat)
    START (hold 1 s) .. ARM   (sticks centred + triggers released, link up)
    START (tap) ....... DISARM when armed
    SELECT or PS ...... E-STOP (disarm + zero thrusters immediately)
    L1 / R1 ........... thrust gain down / up (25-50-75-100 %)
    TRIANGLE .......... toggle all telemetry units SI <-> imperial
    SQUARE ............ drop an operator mark in the event log
    Keyboard SPACE .... E-STOP (when this window has focus)

-----------------------------------------------------------------------------
PROJECT LAYOUT
    rov_console.py ...................... entry point (this file): command-line options, starts the app
    command_center_py/config.py ......... tuning constants: network, rates, deadzones, thruster mix
    command_center_py/gamepad.py ........ DualShock 3 input via SDL2 (pygame), polled in its own thread
    command_center_py/mixer.py .......... stick shaping and thruster mixing (pure maths, no UI)
    command_center_py/link.py ........... UDP command packets out, JSON telemetry in, demo simulator
    command_center_py/ui/theme.py ....... colours, fonts, label helper
    command_center_py/ui/widgets.py ..... custom-painted gauges and composite widgets
    command_center_py/ui/window.py ...... main console window: layout, arming, failsafes, event log

    Wire contract (packet layout) is documented in command_center_py/link.py.
-----------------------------------------------------------------------------
"""

import argparse
import ipaddress
import sys

# Refuse to start outside the project venv or on the wrong Python version.
# Must run before the PySide6/pygame imports below, so the user gets this
# message instead of a confusing "No module named PySide6".
# Skipped in a packaged executable (PyInstaller etc. set sys.frozen), which
# carries its own bundled Python and has no venv.
REQUIRED_PYTHON = (3, 14)
if not getattr(sys, "frozen", False):
    if sys.prefix == sys.base_prefix:
        sys.exit("Not running in the venv - run .venv\\Scripts\\activate first "
                 "(see README).")
    if sys.version_info[:2] != REQUIRED_PYTHON:
        sys.exit(f"Python {REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} required, "
                 f"found {sys.version.split()[0]} - rebuild .venv with "
                 f"py -{REQUIRED_PYTHON[0]}.{REQUIRED_PYTHON[1]} -m venv .venv (see README).")

from PySide6.QtWidgets import QApplication

from command_center_py.config import CMD_PORT, PI_HOST, TELEM_PORT
from command_center_py.ui.window import ConsoleWindow


def ipv4_address(text):
    """argparse type for --host: accept only a usable IPv4 address like 192.168.2.2."""
    text = text.strip()
    try:
        addr = ipaddress.IPv4Address(text)   # strict: exactly 4 parts, each 0-255, no leading zeros
    except ipaddress.AddressValueError:
        raise argparse.ArgumentTypeError(
            f"'{text}' is not a valid IPv4 address - expected four numbers 0-255 "
            f"separated by dots, e.g. 192.168.2.2")
    if addr.is_unspecified or addr == ipaddress.IPv4Address("255.255.255.255") or addr.is_multicast:
        raise argparse.ArgumentTypeError(
            f"'{text}' can't be the Pi's address (unspecified, broadcast or multicast)")
    return str(addr)


def main():
    ap = argparse.ArgumentParser(description="Camosun ROV topside console")
    ap.add_argument("--demo", action="store_true", help="simulate the vehicle (no network)")
    ap.add_argument("--host", type=ipv4_address, default=PI_HOST, metavar="IP",
                    help="IP address of the ROV's Raspberry Pi (default: %(default)s)")
    ap.add_argument("--cmd-port", type=int, default=CMD_PORT,
                    help="UDP port the Pi listens on for thruster commands (default: %(default)s)")
    ap.add_argument("--telem-port", type=int, default=TELEM_PORT,
                    help="UDP port this console listens on for telemetry from the Pi (default: %(default)s)")
    if len(sys.argv) == 1:
        ap.error("no options given - use --demo to simulate, or --host <Pi IP> for the real vehicle "
                 "(see --help)")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    win = ConsoleWindow(args)
    win.show()
    exit_code = app.exec()          # blocks here until the window is closed
    print("CamosunROV Command Centre closed.")
    sys.exit(exit_code)


if __name__ == "__main__":
    print("CamosunROV Command Centre Started.")
    main()