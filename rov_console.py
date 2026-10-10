r"""
Camosun ROV - topside control console
PySide6 UI + DualShock 3 input (SDL2 via pygame)

Control chain:  DualShock 3 -> this laptop (Windows) -> UDP -> Raspberry Pi -> STM32 -> thrusters

Run (Python 3.14, inside the repo's .venv - see README for first-time setup):
    .venv\Scripts\activate          # once per terminal
    py rov_console.py                # no options - the program opens on the main menu

MAIN MENU
    CONNECT VEHICLE ... enter (or load a saved profile for) the Pi's IP address and UDP
                        ports, then CONNECT. The console opens once the Pi answers;
                        after 5 s with no answer the dialog stays open so you can retry.
                        Profiles are saved in vehicle_profiles/ (one JSON file each).
    DEMO MODE ......... simulated vehicle and telemetry, nothing transmitted
    CONTROLLER MAP .... DualShock 3 and Xbox button maps
    QUIT .............. exit
    Closing the console window returns to the main menu - only allowed while DISARMED.
    Ctrl+C in this terminal disarms, sends zero-thrust frames and exits from anywhere.

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
    rov_console.py ...................... entry point (this file): venv check, starts the app
    command_center_py/app.py ............ switches between the main menu and the console
    command_center_py/config.py ......... tuning constants: network defaults, rates, deadzones, thruster mix
    command_center_py/profiles.py ....... saved vehicle profiles (vehicle_profiles/*.json)
    command_center_py/gamepad.py ........ DualShock 3 input via SDL2 (pygame), polled in its own thread
    command_center_py/mixer.py .......... stick shaping and thruster mixing (pure maths, no UI)
    command_center_py/link.py ........... UDP command packets out, JSON telemetry in, demo simulator
    command_center_py/ui/theme.py ....... colours, fonts, label helper
    command_center_py/ui/widgets.py ..... custom-painted gauges and composite widgets
    command_center_py/ui/menu.py ........ main menu, CONNECT VEHICLE and CONTROLLER MAP dialogs
    command_center_py/ui/window.py ...... main console window: layout, arming, failsafes, event log

    Wire contract (packet layout) is documented in command_center_py/link.py.
-----------------------------------------------------------------------------
"""

import os
import signal
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

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from command_center_py.app import RovApp


def install_ctrl_c_handler(app, rov):
    """Let Ctrl+C in the terminal shut the program down cleanly.

    While app.exec() runs, Qt's C++ event loop owns the main thread and Python's
    default SIGINT handler only raises KeyboardInterrupt inside whatever Qt
    callback happens to run next, where PySide swallows it - so Ctrl+C did
    nothing. Instead, catch SIGINT ourselves and shut down through the normal
    path: if the console is open it is force-closed, which disarms and sends the
    zero-thrust frames to the Pi, then the menu closes and the gamepad stops.

    Python only runs signal handlers when the interpreter gets control back from
    Qt. The windows' timers already do that many times a second, but a small
    keep-alive timer is added so this works even if those are stopped.

    Press Ctrl+C a second time to force-quit if a clean close ever hangs.
    """
    state = {"pressed": False}

    def on_sigint(signum, frame):
        if state["pressed"]:
            print("\nSecond Ctrl+C - forcing exit.")
            os._exit(130)
        state["pressed"] = True
        print("\nCtrl+C received - disarming and closing (press again to force quit)...")
        rov.shutdown()     # console (if open): disarm, zero thrusters; then close the menu
        app.quit()

    signal.signal(signal.SIGINT, on_sigint)

    keepalive = QTimer(app)
    keepalive.timeout.connect(lambda: None)   # hands control back to Python so the handler can run
    keepalive.start(200)


def use_own_taskbar_icon():
    """Windows groups a Python script under python.exe's icon in the taskbar unless the
    process has its own app ID - set one so the taskbar shows the CamosunROV logo."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CamosunROV.CommandCentre")
        except (AttributeError, OSError):
            pass


def main():
    if len(sys.argv) > 1:
        sys.exit("rov_console.py takes no options - run it as:  py rov_console.py\n"
                 "Choose CONNECT VEHICLE or DEMO MODE in the main menu.")
    print("CamosunROV Command Centre Started.")
    use_own_taskbar_icon()
    app = QApplication(sys.argv)
    rov = RovApp()
    rov.start()
    install_ctrl_c_handler(app, rov)
    exit_code = app.exec()          # blocks here until the main menu is closed (QUIT)
    rov.cleanup()
    print("CamosunROV Command Centre closed.")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
