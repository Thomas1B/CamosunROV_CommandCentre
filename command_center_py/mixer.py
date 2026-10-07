"""Stick shaping and thruster mixing - pure maths, no UI or networking."""

import math

from command_center_py.config import DEADZONE, EXPO, THRUSTERS, TRIGGER_DEADZONE


def shape(v):
    """Apply the stick deadzone and expo curve to one axis (-1..1)."""
    a = abs(v)
    if a < DEADZONE:
        return 0.0
    a = (a - DEADZONE) / (1 - DEADZONE)
    a = (1 - EXPO) * a + EXPO * a ** 3
    return math.copysign(a, v)


def trigger(v):
    """Remove the L2/R2 rest noise and rescale to 0..1."""
    return 0.0 if v < TRIGGER_DEADZONE else (v - TRIGGER_DEADZONE) / (1 - TRIGGER_DEADZONE)


def mix(pad, gain_pct):
    """Turn a PadState into six thruster commands, -gain_pct..+gain_pct percent."""
    heave = trigger(pad.r2) - trigger(pad.l2)        # R2 up, L2 down
    axes = (shape(pad.ly), shape(pad.lx), heave, shape(pad.rx))
    raw = [sum(c * a for c, a in zip(coef, axes)) for _, _, _, coef in THRUSTERS]
    out = [0.0] * len(raw)
    for grp in ("H", "V"):
        idx = [i for i, t in enumerate(THRUSTERS) if t[2] == grp]
        peak = max([1.0] + [abs(raw[i]) for i in idx])
        for i in idx:
            out[i] = raw[i] / peak
    return [int(round(x * gain_pct)) for x in out]
