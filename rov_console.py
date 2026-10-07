#!/usr/bin/env python3
"""
Camosun ROV - topside control console
PySide6 UI + DualShock 3 input (SDL2 via pygame)

Control chain:  DualShock 3 -> this laptop (Windows) -> UDP -> Raspberry Pi -> STM32 -> thrusters

Run:
    py -m pip install PySide6                 # one-time (pygame-ce already installed)
    py rov_console.py --demo                  # no vehicle needed, simulated telemetry
    py rov_console.py --host 192.168.2.2      # real vehicle
    py rov_console.py --cmd-port 5600         # UDP port the Pi listens on for commands (default 5600)
    py rov_console.py --telem-port 5601       # UDP port this console listens on for telemetry (default 5601)
    py rov_console.py --help                  # list all options

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
import sys

from PySide6.QtWidgets import QApplication

from command_center_py.config import CMD_PORT, PI_HOST, TELEM_PORT
from command_center_py.ui.window import ConsoleWindow


def main():
    ap = argparse.ArgumentParser(description="Camosun ROV topside console")
    ap.add_argument("--demo", action="store_true", help="simulate the vehicle (no network)")
    ap.add_argument("--host", default=PI_HOST,
                    help="IP address of the ROV's Raspberry Pi (default: %(default)s)")
    ap.add_argument("--cmd-port", type=int, default=CMD_PORT,
                    help="UDP port the Pi listens on for thruster commands (default: %(default)s)")
    ap.add_argument("--telem-port", type=int, default=TELEM_PORT,
                    help="UDP port this console listens on for telemetry from the Pi (default: %(default)s)")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    win = ConsoleWindow(args)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
