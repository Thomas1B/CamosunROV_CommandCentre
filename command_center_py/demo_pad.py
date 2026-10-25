"""Simulated controller for DEMO MODE.

When the console runs in demo mode and no real controller is plugged in, DemoPad
stands in for the Gamepad: it returns the same PadState snapshots, so everything
downstream (arming, mixing, tilt, gain, units, marks, chips, sticks) runs exactly
as it would with a real pad. Plug a real controller in and it takes over at once.

Script (matches the UI design's simulated input):
    0-3 s ............ sticks centred, hold START ~1.4 s -> ARM
    then, 40 s loop .. sticks and triggers sweep smoothly
                       R1 at 8 s, L1 at 22 s (gain up / down)
                       D-pad up x3 at 12 s, down x3 at 27 s (camera tilt)
                       SQUARE at 17 s (operator mark)
                       TRIANGLE at 31 s and 35 s (units on / off)
                       CROSS held 5-10.5 s (zero depth, 5 s averaged), again 36-37.5 s (clear)
    when disarmed .... (E-STOP, START tap, menu) centre the sticks, wait 2 s,
                       hold START to re-arm
"""

import math
import time

from command_center_py.gamepad import PAD_BUTTONS, PadState


class DemoPad:
    def __init__(self, real_pad, is_armed, name="Simulated controller (demo)"):
        """real_pad: the shared Gamepad. is_armed: callable returning the console's armed state."""
        self.real = real_pad
        self.is_armed = is_armed
        self.name = name
        self.error = None            # the real pad's errors are reported by the menu, not here
        self.t0 = time.monotonic()
        self._disarmed_at = None

    def snapshot(self) -> PadState:
        real = self.real.snapshot()
        if real.connected:
            return real
        return self._simulate(time.monotonic() - self.t0)

    def close(self):
        pass                         # the real Gamepad is owned and closed by the app

    def _simulate(self, t):
        b = dict.fromkeys(PAD_BUTTONS, False)
        lx = ly = rx = l2 = r2 = 0.0

        def tap(p, at):
            return at <= p < at + 0.15

        if t < 3.0:
            b["start"] = 1.2 <= t < 2.6                       # hold START -> ARM
        elif not self.is_armed():
            # disarmed: centre the sticks, wait 2 s, hold START to re-arm (retry every 4 s)
            if self._disarmed_at is None:
                self._disarmed_at = t
            d = t - self._disarmed_at
            b["start"] = 2.0 <= d < 3.4
            if d >= 4.0:
                self._disarmed_at = t
        else:
            self._disarmed_at = None
            w = t - 3.0
            p = w % 40.0
            ease = min(1.0, w / 2.0)                          # sticks ease in after arming
            lx = ease * 0.65 * math.sin(w * 0.55)             # sway
            ly = ease * 0.85 * math.sin(w * 0.33 + 1.0)       # surge (up = positive)
            rx = ease * 0.60 * math.sin(w * 0.21 + 2.0)       # yaw
            h = math.sin(w * 0.42)                            # heave: R2 up / L2 down
            if h > 0.15:
                r2 = ease * h
            elif h < -0.15:
                l2 = ease * -h
            b["r1"] = tap(p, 8.0)
            b["l1"] = tap(p, 22.0)
            b["up"] = any(tap(p, a) for a in (12.0, 12.6, 13.2))
            b["down"] = any(tap(p, a) for a in (27.0, 27.6, 28.2))
            b["square"] = tap(p, 17.0)
            b["triangle"] = tap(p, 31.0) or tap(p, 35.0)
            b["cross"] = 5.0 <= p < 10.5 or 36.0 <= p < 37.5

        return PadState(connected=True, name=self.name, mode="SDL",
                        lx=lx, ly=ly, rx=rx, ry=0.0, l2=l2, r2=r2, buttons=b)
