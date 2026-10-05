"""
Camosun ROV - Command Center (laptop side)

DualShock 3 -> deadband -> thruster mixing -> PWM values -> UDP packet to the Pi

Controls:
  Left stick  up/down     Surge (forward/back)
  Left stick  left/right  Yaw (turn)
  Right stick up/down     Heave (up/down)
  Right stick left/right  Sway (strafe)
  Start                   Arm (sticks must be centred)
  Select                  Disarm / emergency stop
  L1 / R1                 Power limit down / up

Run:  py rov_control.py      Quit: Ctrl+C
"""
import os
os.environ["SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"] = "1"

import socket
import struct
import time
import pygame

# ============================== CONFIG ==============================
DRY_RUN = True                 # True = print only. Set False once the Pi receiver is running.
PI_IP, PI_PORT = "192.168.2.2", 5005
SEND_HZ = 20
DEADBAND = 0.20                # this DS3 drifts up to ~0.15 at rest

# Controller mapping (measured on this DS3)
AX_YAW, AX_SURGE, AX_SWAY, AX_HEAVE = 0, 1, 2, 3
INVERT_SURGE = True            # stick up reads negative -> flip so up = forward
INVERT_HEAVE = True            # stick up reads negative -> flip so up = rise
BTN_POWER_DOWN, BTN_POWER_UP = 4, 5      # L1, R1
BTN_DISARM, BTN_ARM = 6, 7               # Select, Start

POWER_LEVELS = [0.25, 0.50, 0.75, 1.00]  # always starts at 25%

# ESC pulse widths in microseconds: 1500 = stop, 1100..1900 = full reverse..forward
PWM_NEUTRAL, PWM_RANGE = 1500, 400

# Thruster table. Packet order = STM32 output order (channel 0..5).
# Coefficients say how much each motion drives that thruster.
# DIR flips a thruster whose prop/wiring pushes the wrong way (set during bench test).
#                name  surge  sway  yaw  heave  DIR
THRUSTERS = [
    ("FL",   1,    1,    1,   0,    1),   # front-left  horizontal (vectored)
    ("FR",   1,   -1,   -1,   0,    1),   # front-right horizontal (vectored)
    ("RL",   1,   -1,    1,   0,    1),   # rear-left   horizontal (vectored)
    ("RR",   1,    1,   -1,   0,    1),   # rear-right  horizontal (vectored)
    ("VF",   0,    0,    0,   1,    1),   # front vertical
    ("VR",   0,    0,    0,   1,    1),   # rear vertical
]
# ====================================================================


def shape(x):
    """Deadband, then rescale so output still reaches +/-1 at full stick."""
    if abs(x) < DEADBAND:
        return 0.0
    mag = (abs(x) - DEADBAND) / (1.0 - DEADBAND)
    return min(mag, 1.0) * (1 if x > 0 else -1)


def mix(surge, sway, yaw, heave, power):
    """Return one command (-1..+1) per thruster.
    Horizontal and vertical groups are normalised separately, so full
    heave is never reduced just because you are also turning."""
    raw = [t[1]*surge + t[2]*sway + t[3]*yaw + t[4]*heave for t in THRUSTERS]
    horiz = [i for i, t in enumerate(THRUSTERS) if t[4] == 0]
    vert = [i for i, t in enumerate(THRUSTERS) if t[4] != 0]
    out = raw[:]
    for group in (horiz, vert):
        peak = max([1.0] + [abs(raw[i]) for i in group])
        for i in group:
            out[i] = raw[i] / peak
    return [THRUSTERS[i][5] * out[i] * power for i in range(len(THRUSTERS))]


def to_us(x):
    x = max(-1.0, min(1.0, x))
    return int(round(PWM_NEUTRAL + PWM_RANGE * x))


def main():
    pygame.init()
    pygame.joystick.init()
    sock = None if DRY_RUN else socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    js = None
    armed = False
    power_idx = 0
    seq = 0
    period = 1.0 / SEND_HZ
    next_t = time.perf_counter()

    print(f"{'DRY RUN - nothing is sent' if DRY_RUN else f'Sending to {PI_IP}:{PI_PORT}'}")
    print("Waiting for controller... (Ctrl+C to quit)")

    try:
        while True:
            for ev in pygame.event.get():
                if ev.type == pygame.JOYDEVICEADDED and js is None:
                    js = pygame.joystick.Joystick(ev.device_index)
                    print(f"\nConnected: {js.get_name()}")
                elif ev.type == pygame.JOYDEVICEREMOVED and js is not None:
                    if ev.instance_id == js.get_instance_id():
                        js, armed = None, False
                        print("\nController lost - DISARMED")
                elif ev.type == pygame.JOYBUTTONDOWN and js is not None:
                    if ev.button == BTN_DISARM:
                        armed = False
                    elif ev.button == BTN_ARM:
                        centred = all(abs(js.get_axis(a)) < DEADBAND
                                      for a in (AX_YAW, AX_SURGE, AX_SWAY, AX_HEAVE))
                        if centred:
                            armed = True
                        else:
                            print("\nCentre the sticks before arming")
                    elif ev.button == BTN_POWER_UP:
                        power_idx = min(power_idx + 1, len(POWER_LEVELS) - 1)
                    elif ev.button == BTN_POWER_DOWN:
                        power_idx = max(power_idx - 1, 0)

            if js is not None and armed:
                surge = shape(js.get_axis(AX_SURGE)) * (-1 if INVERT_SURGE else 1)
                heave = shape(js.get_axis(AX_HEAVE)) * (-1 if INVERT_HEAVE else 1)
                yaw = shape(js.get_axis(AX_YAW))
                sway = shape(js.get_axis(AX_SWAY))
                cmds = mix(surge, sway, yaw, heave, POWER_LEVELS[power_idx])
                pwm = [to_us(c) for c in cmds]
            else:
                pwm = [PWM_NEUTRAL] * len(THRUSTERS)

            packet = struct.pack("<I6H", seq, *pwm)
            if sock:
                sock.sendto(packet, (PI_IP, PI_PORT))
            seq = (seq + 1) & 0xFFFFFFFF

            state = "ARMED" if armed else "SAFE "
            vals = "  ".join(f"{t[0]}:{p}" for t, p in zip(THRUSTERS, pwm))
            print(f"\r{state} PWR {int(POWER_LEVELS[power_idx]*100):3d}%  {vals}   ",
                  end="", flush=True)

            next_t += period
            time.sleep(max(0.0, next_t - time.perf_counter()))

    except KeyboardInterrupt:
        print("\nStopping - sending neutral")
    finally:
        if sock:
            neutral = struct.pack("<I6H", seq, *[PWM_NEUTRAL] * len(THRUSTERS))
            for _ in range(5):
                sock.sendto(neutral, (PI_IP, PI_PORT))
                time.sleep(0.02)
        pygame.quit()


if __name__ == "__main__":
    main()
