"""Tuning constants for the topside console - adjust these on the bench."""

APP_VERSION = "0.5.0"

PI_HOST = "192.168.2.2"
CMD_PORT = 5600
TELEM_PORT = 5601
RATE_HZ = 50

DEADZONE = 0.20          # stick deadzone - Josh's DS3 rests at up to ~0.17 on A1/A2
EXPO = 0.30              # 0 = linear, 1 = full cubic (finer control near centre)
GAIN_STEPS = (25, 50, 75, 100)
DEFAULT_GAIN_INDEX = 1   # start at 50 %
TRIGGER_DEADZONE = 0.06  # L2/R2 rest noise
TILT_MIN, TILT_MAX = -45, 45   # camera servo limits in degrees - match the Pi/servo
TILT_STEP = 5
ARM_HOLD_S = 1.0
LINK_TIMEOUT_S = 1.0
LOSS_PRINT_S = 10        # print lost-packet count to the terminal every this many seconds
REQUIRE_LINK_TO_ARM = True   # set False to bench-test before telemetry exists

# Thruster mix: (name, role, group, (surge, sway, heave, yaw))
#   surge = left stick Y, sway = left stick X, heave = R2 - L2, yaw = right stick X
# Group "H" and "V" are normalised separately so full surge doesn't steal heave.
# !! VERIFY SIGNS ON THE BENCH WITH PROPS OFF - flip a coefficient's sign
# !! (or the whole row, for a reversed prop) until each stick does the right thing.
THRUSTERS = [
    ("T1", "FWD-PORT",  "H", (1,  1, 0,  1)),
    ("T2", "FWD-STBD",  "H", (1, -1, 0, -1)),
    ("T3", "AFT-PORT",  "H", (1, -1, 0,  1)),
    ("T4", "AFT-STBD",  "H", (1,  1, 0, -1)),
    ("T5", "VERT-PORT", "V", (0,  0, 1,  0)),
    ("T6", "VERT-STBD", "V", (0,  0, 1,  0)),
]