"""Stick shaping and thruster mixing - pure maths, no UI or networking."""

import math

from command_center_py.config import DEADZONE, EXPO, THRUSTERS, TRIGGER_DEADZONE


def shape(v, deadzone=DEADZONE):
    """Apply the stick deadzone and expo curve to one axis (-1..1)."""
    a = abs(v)
    if a < deadzone:
        return 0.0
    a = (a - deadzone) / (1 - deadzone)
    a = (1 - EXPO) * a + EXPO * a ** 3
    return math.copysign(a, v)


def trigger(v, deadzone=TRIGGER_DEADZONE):
    """Remove the L2/R2 rest noise and rescale to 0..1."""
    return 0.0 if v < deadzone else (v - deadzone) / (1 - deadzone)


def mix(pad, gain_pct, dz=None):
    """Turn a PadState into six thruster commands, -gain_pct..+gain_pct percent.
    dz: per-axis deadzones from a controller profile ({"lx": .., "ly": .., "rx": .., "l2": .., "r2": ..});
    None = DEADZONE / TRIGGER_DEADZONE from config.py."""
    d = lambda k, default: default if dz is None else dz.get(k, default)
    heave = trigger(pad.r2, d("r2", TRIGGER_DEADZONE)) - trigger(pad.l2, d("l2", TRIGGER_DEADZONE))   # R2 up, L2 down
    axes = (shape(pad.ly, d("ly", DEADZONE)), shape(pad.lx, d("lx", DEADZONE)), heave, shape(pad.rx, d("rx", DEADZONE)))
    raw = [sum(c * a for c, a in zip(coef, axes)) for _, _, _, coef in THRUSTERS]
    out = [0.0] * len(raw)
    for grp in ("H", "V"):
        idx = [i for i, t in enumerate(THRUSTERS) if t[2] == grp]
        peak = max([1.0] + [abs(raw[i]) for i in idx])
        for i in idx:
            out[i] = raw[i] / peak
    return [int(round(x * gain_pct)) for x in out]
