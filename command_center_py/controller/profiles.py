"""Controller profiles: per-controller stick and trigger calibration.

One JSON file per profile in <top dir>/controller_profiles/ (config.CONTROLLER_PROFILES_DIR).
Made and edited on the main menu's CONTROLLER PROFILES page; chosen in CONNECT VEHICLE
(default: none, i.e. the config.py defaults). "controller" is only a note of which
controller the profile was made for (filled in from the connected one when calibrating).

File contents, e.g. controller_profiles/Josh_DS3.json (raw SDL axis values, -1..1 / 0..1):
    {"name": "Josh DS3", "controller": "PS3 Controller",
     "axes": {"lx": {"center": 0.031, "deadzone": 0.08, "min": -0.97, "max": 0.99},
              "ly": {...}, "rx": {...}, "ry": {...}},
     "triggers": {"l2": {"rest": 0.0, "max": 1.0, "deadzone": 0.04}, "r2": {...}},
     "saved": "2026-11-01T16:40:12-07:00"}

How a profile changes the input (CalibratedPad.snapshot):
    stick axis  v = (raw - center) / (max - center)   when raw >= center
                v = (raw - center) / (center - min)   when raw <  center      -> clamped -1..1
                so the resting stick reads 0 (drift removed) and full throw reads exactly +-1.
    trigger     v = (raw - rest) / (max - rest)                                 -> clamped 0..1
    The deadzones are then applied by the mixer (mixer.shape / mixer.trigger) on these
    calibrated values, in place of DEADZONE / TRIGGER_DEADZONE from config.py.
Without a profile the console behaves exactly as before (config.py defaults).
"""

import dataclasses
import json
import math
import random
import re
import time
from datetime import datetime

from command_center_py.config import CONTROLLER_PROFILES_DIR, DEADZONE, TRIGGER_DEADZONE

AXES = ("lx", "ly", "rx", "ry")
TRIGGERS = ("l2", "r2")
AXIS_NAMES = {"lx": "Left X", "ly": "Left Y", "rx": "Right X", "ry": "Right Y", "l2": "L2 / LT", "r2": "R2 / RT"}

NONE = "none"                    # picker choice for "no profile"; anything else is a profile name

# Calibration wizard rules
MIN_DEADZONE = 0.03              # never below this, even for a perfectly quiet stick
DEADZONE_MARGIN = 0.03           # added on top of the measured rest noise
MAX_DEADZONE = 0.40
MIN_RANGE = 0.30                 # an axis that moved less than this didn't really get calibrated


def default_axis():
    return {"center": 0.0, "deadzone": DEADZONE, "min": -1.0, "max": 1.0}


def default_trigger():
    return {"rest": 0.0, "max": 1.0, "deadzone": TRIGGER_DEADZONE}


def _num(v, lo, hi, fallback):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return fallback
    return max(lo, min(hi, v))


class ControllerProfile:
    def __init__(self, name="", controller="", axes=None, triggers=None, saved=""):
        self.name = name
        self.controller = controller
        self.axes = {k: default_axis() for k in AXES}
        self.triggers = {k: default_trigger() for k in TRIGGERS}
        self.saved = saved
        for k, a in (axes or {}).items():
            if k in self.axes and isinstance(a, dict):
                d = self.axes[k]
                d["center"] = _num(a.get("center"), -0.5, 0.5, d["center"])
                d["deadzone"] = _num(a.get("deadzone"), 0.0, MAX_DEADZONE, d["deadzone"])
                d["min"] = _num(a.get("min"), -1.0, d["center"] - 0.05, d["min"])
                d["max"] = _num(a.get("max"), d["center"] + 0.05, 1.0, d["max"])
        for k, t in (triggers or {}).items():
            if k in self.triggers and isinstance(t, dict):
                d = self.triggers[k]
                d["rest"] = _num(t.get("rest"), 0.0, 0.5, d["rest"])
                d["max"] = _num(t.get("max"), d["rest"] + 0.1, 1.0, d["max"])
                d["deadzone"] = _num(t.get("deadzone"), 0.0, MAX_DEADZONE, d["deadzone"])

    def copy(self):
        return ControllerProfile.from_dict(self.to_dict())

    # ---- applying ----
    def axis(self, k, raw):
        a = self.axes[k]
        c = a["center"]
        if raw >= c:
            v = (raw - c) / max(1e-6, a["max"] - c)
        else:
            v = (raw - c) / max(1e-6, c - a["min"])
        return max(-1.0, min(1.0, v))

    def trigger(self, k, raw):
        t = self.triggers[k]
        return max(0.0, min(1.0, (raw - t["rest"]) / max(1e-6, t["max"] - t["rest"])))

    def apply(self, st):
        """Calibrated copy of a PadState (sticks centred and full-range, triggers 0..1)."""
        if not st.connected:
            return st
        return dataclasses.replace(st, lx=self.axis("lx", st.lx), ly=self.axis("ly", st.ly),
                                   rx=self.axis("rx", st.rx), ry=self.axis("ry", st.ry),
                                   l2=self.trigger("l2", st.l2), r2=self.trigger("r2", st.r2))

    def deadzones(self):
        dz = {k: self.axes[k]["deadzone"] for k in AXES}
        dz.update({k: self.triggers[k]["deadzone"] for k in TRIGGERS})
        return dz

    # ---- JSON ----
    def to_dict(self):
        r = lambda v: round(v, 4)
        return {"name": self.name, "controller": self.controller,
                "axes": {k: {f: r(v) for f, v in a.items()} for k, a in self.axes.items()},
                "triggers": {k: {f: r(v) for f, v in t.items()} for k, t in self.triggers.items()},
                "saved": self.saved}

    @classmethod
    def from_dict(cls, d):
        return cls(str(d.get("name", "")).strip(), str(d.get("controller", "")).strip(),
                   d.get("axes"), d.get("triggers"), str(d.get("saved", "")))


def default_deadzones():
    dz = {k: DEADZONE for k in AXES}
    dz.update({k: TRIGGER_DEADZONE for k in TRIGGERS})
    return dz


# ---------------------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------------------
def _file_for(name):
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "controller"
    return CONTROLLER_PROFILES_DIR / f"{safe}.json"


def load_all():
    """Every saved profile, sorted by name. Unreadable files are skipped."""
    out = []
    if CONTROLLER_PROFILES_DIR.is_dir():
        for p in CONTROLLER_PROFILES_DIR.glob("*.json"):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(d, dict) and str(d.get("name", "")).strip():
                out.append(ControllerProfile.from_dict(d))
    return sorted(out, key=lambda p: p.name.lower())


def save(profile):
    """Writes the profile (replacing one with the same name). Raises OSError on failure."""
    CONTROLLER_PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    profile.saved = datetime.now().astimezone().isoformat(timespec="seconds")
    _file_for(profile.name).write_text(json.dumps(profile.to_dict(), indent=2) + "\n", encoding="utf-8")


def delete(name):
    try:
        _file_for(name).unlink()
    except FileNotFoundError:
        pass


def describe(choice):
    return "Defaults (no calibration)" if choice == NONE else choice


# ---------------------------------------------------------------------------------------
# Calibrated pad
# ---------------------------------------------------------------------------------------
class CalibratedPad:
    """Wraps the shared Gamepad and applies a controller profile to every snapshot.

    choice: NONE (config.py defaults, no calibration) or a saved profile's name.
    `profile` is the profile in use right now (None = defaults); `deadzones()` gives the
    mixer's per-axis deadzones. Profiles are read from disk when this is created.
    """

    def __init__(self, pad, choice=NONE):
        self.base = pad
        self.choice = choice or NONE
        self._profiles = load_all()
        self._name = None
        self.profile = None
        self.missing = self.choice != NONE and not any(p.name == self.choice for p in self._profiles)

    def __getattr__(self, attr):                 # error, close, ... from the real pad
        return getattr(self.base, attr)

    def _resolve(self, name):
        if self.choice == NONE:
            return None
        return next((p for p in self._profiles if p.name == self.choice), None)

    def snapshot(self):
        st = self.base.snapshot()
        if st.name != self._name:                # controller (re)connected: apply the chosen profile
            self._name = st.name
            self.profile = self._resolve(st.name) if st.connected else self.profile
        return self.profile.apply(st) if (self.profile is not None and st.connected) else st

    def deadzones(self):
        """Per-axis deadzones for the mixer: the profile's while its controller is connected,
        else config.py defaults (e.g. demo mode's simulated pad)."""
        if self.profile is None or not self.base.snapshot().connected:
            return default_deadzones()
        return self.profile.deadzones()

    def status(self):
        """One line for the event log: which profile is in use and why."""
        if self.profile is None:
            if self.missing:
                return f'Controller profile "{self.choice}" not found — using defaults'
            return "No controller profile — using default deadzones"
        return f'Controller profile "{self.profile.name}"'


# ---------------------------------------------------------------------------------------
# Calibration wizard (pure logic; the page shows it)
# ---------------------------------------------------------------------------------------
class Calibration:
    """The CALIBRATE wizard, fed raw PadState samples:
        ready      "hands off the controller, then press OK"
        left_flick 1a  flick the left stick from FLICKS random directions -> centre + deadzone
        left_cw    1b  left stick clockwise, TURNS full turns                -> min / max
        left_ccw   1c  left stick counter-clockwise, TURNS turns
        right_*    2a-2c  the same for the right stick
        triggers   3   press both triggers fully, then release              -> max per trigger
    Trigger rest + jitter are measured while the sticks settle during the flicks (the
    triggers are untouched then), so there is no separate rest step.

    FLICK: the page shows a direction; push the stick out past FLICK_OUT that way (within
    45 degrees) and let go. Once it is back inside SETTLE_R and has stayed still (spread
    < STILL over SETTLE_N samples, or SETTLE_MAX_S has passed) the settled position is
    recorded. The centre is the mean of the settled points; the deadzone covers the one
    furthest from it plus the jitter - so wherever the spring leaves the stick, it reads 0.

    ROTATE: a turn only counts while the stick is pushed out past EDGE from its centre, so
    wiggling near the middle doesn't count; turning the wrong way takes turns back off
    (never below 0). Each rotate / flick step moves on by itself when done; next() skips."""

    STEPS = ("ready", "left_flick", "left_cw", "left_ccw", "right_flick", "right_cw", "right_ccw", "triggers")
    STICK_AXES = {"l": ("lx", "ly"), "r": ("rx", "ry")}
    ROTATE = {"left_cw": ("lx", "ly", -1), "left_ccw": ("lx", "ly", 1),     # (x axis, y axis, direction:
              "right_cw": ("rx", "ry", -1), "right_ccw": ("rx", "ry", 1)}  #  +1 = counter-clockwise, y up)
    FLICK = ("left_flick", "right_flick")
    DIRECTIONS = {0: "→", 45: "↗", 90: "↑", 135: "↖", 180: "←", 225: "↙", 270: "↓", 315: "↘"}
    FLICKS = 12
    TURNS = 10
    EDGE = 0.5
    FLICK_OUT = 0.7          # how far out a flick has to go (raw, from the middle)
    SETTLE_R = 0.35          # back inside this = released
    STILL = 0.01             # settled = spread below this over SETTLE_N samples
    SETTLE_N = 6             # ~0.3 s at the menu's 20 Hz
    SETTLE_MAX_S = 1.5

    def __init__(self, seed=None):
        self.step = 0
        self.t0 = time.monotonic()
        self.rng = random.Random(seed)
        self.settled = {"l": [], "r": []}            # settled (x, y) per stick
        self.jitter = {k: 0.0 for k in AXES + TRIGGERS}
        self.trig_rest = {k: [] for k in TRIGGERS}
        self.lo = {k: 0.0 for k in AXES}
        self.hi = {k: 0.0 for k in AXES}
        self.tmax = {k: 0.0 for k in TRIGGERS}
        self._reset_step()

    def _reset_step(self):
        self._angle = None             # rotate: last stick angle (radians) while past EDGE
        self._swept = 0.0              # rotate: signed angle swept this step, + = counter-clockwise
        self.phase = "push"            # flick: push -> back -> settle
        self.target = None             # flick: direction in degrees
        self._win = []                 # flick: recent samples while settling
        self._t_back = 0.0
        if self.name in self.FLICK:
            self._new_target()

    def _new_target(self):
        choices = [d for d in self.DIRECTIONS if d != self.target]
        self.target = self.rng.choice(choices)
        self.phase = "push"

    @property
    def name(self):
        return self.STEPS[self.step] if self.step < len(self.STEPS) else "done"

    def stick(self):
        """'l' or 'r' while a stick is being flicked or rotated, else None."""
        return self.name[0] if (self.name in self.ROTATE or self.name in self.FLICK) else None

    def turns(self):
        """Full turns done in the asked direction this step (0..TURNS)."""
        if self.name not in self.ROTATE:
            return 0
        return min(self.TURNS, max(0, int(self._swept * self.ROTATE[self.name][2] / (2 * math.pi))))

    def flicks(self):
        s = self.stick()
        return len(self.settled[s]) if (s and self.name in self.FLICK) else 0

    def arrow(self):
        return self.DIRECTIONS.get(self.target, "")

    def centre(self, k):
        """Centre so far for a stick axis (mean of settled flicks), 0.0 before any."""
        s = "l" if k in ("lx", "ly") else "r"
        pts = self.settled[s]
        if not pts:
            return 0.0
        i = 0 if k in ("lx", "rx") else 1
        return sum(p[i] for p in pts) / len(pts)

    def trigger_rest(self, k):
        s = self.trig_rest[k]
        return sum(s) / len(s) if s else 0.0

    def feed(self, st, now=None):
        now = time.monotonic() if now is None else now
        if not st.connected:
            return
        v = {"lx": st.lx, "ly": st.ly, "rx": st.rx, "ry": st.ry, "l2": st.l2, "r2": st.r2}
        if self.name in self.FLICK:
            self._feed_flick(v, now)
        elif self.name in self.ROTATE:
            kx, ky, _ = self.ROTATE[self.name]
            for k in (kx, ky):
                self.lo[k], self.hi[k] = min(self.lo[k], v[k]), max(self.hi[k], v[k])
            dx, dy = v[kx] - self.centre(kx), v[ky] - self.centre(ky)
            if math.hypot(dx, dy) < self.EDGE:
                self._angle = None      # back near the middle: don't count a jump across it
            else:
                a = math.atan2(dy, dx)
                if self._angle is not None:
                    d = (a - self._angle + math.pi) % (2 * math.pi) - math.pi    # -pi..pi
                    want = self.ROTATE[self.name][2]
                    self._swept = want * max(0.0, (self._swept + d) * want)   # wrong way: back to 0, no debt
                self._angle = a
            if self.turns() >= self.TURNS:
                self.next(now)
        elif self.name == "triggers":
            for k in TRIGGERS:
                self.tmax[k] = max(self.tmax[k], v[k])

    def _feed_flick(self, v, now):
        s = self.stick()
        kx, ky = self.STICK_AXES[s]
        x, y = v[kx], v[ky]
        r = math.hypot(x, y)
        if self.phase == "push":
            if r >= self.FLICK_OUT:
                a = math.degrees(math.atan2(y, x)) % 360
                if abs((a - self.target + 180) % 360 - 180) <= 45:
                    self.phase = "back"
        elif self.phase == "back":
            if r < self.SETTLE_R:
                self.phase, self._win, self._t_back = "settle", [], now
        elif self.phase == "settle":
            if r >= self.SETTLE_R:                   # pushed again before it settled: start over
                self.phase = "back"
                return
            self._win = (self._win + [v])[-self.SETTLE_N:]
            xs, ys = [w[kx] for w in self._win], [w[ky] for w in self._win]
            still = len(self._win) == self.SETTLE_N and max(max(xs) - min(xs), max(ys) - min(ys)) < self.STILL
            if still or now - self._t_back >= self.SETTLE_MAX_S:
                n = len(self._win)
                self.settled[s].append((sum(xs) / n, sum(ys) / n))
                for k, vals in ((kx, xs), (ky, ys)):
                    self.jitter[k] = max(self.jitter[k], max(vals) - min(vals))
                for k in TRIGGERS:                  # triggers are untouched while flicking
                    vals = [w[k] for w in self._win]
                    self.trig_rest[k] += vals
                    self.jitter[k] = max(self.jitter[k], max(vals) - min(vals))
                if len(self.settled[s]) >= self.FLICKS:
                    self.next(now)
                else:
                    self._new_target()

    def next(self, now=None):
        self.step += 1
        self.t0 = time.monotonic() if now is None else now
        self._reset_step()

    def warnings(self):
        w = []
        for s, label in (("l", "Left stick"), ("r", "Right stick")):
            if len(self.settled[s]) < 3:
                w.append(f"{label}: only {len(self.settled[s])} flicks — kept its old centre and deadzone")
        w += [f"{AXIS_NAMES[k]} barely moved — kept its old range" for k in AXES if self.hi[k] - self.lo[k] < MIN_RANGE]
        w += [f"{AXIS_NAMES[k]} not pressed fully" for k in TRIGGERS
              if self.tmax[k] - self.trigger_rest(k) < MIN_RANGE]
        return w

    def result(self, profile):
        p = profile.copy()
        for k in AXES:
            s = "l" if k in ("lx", "ly") else "r"
            a = p.axes[k]
            pts = self.settled[s]
            if len(pts) >= 3:                                # enough flicks for a centre
                c = self.centre(k)
                i = 0 if k in ("lx", "rx") else 1
                spread = max(abs(pt[i] - c) for pt in pts)  # furthest settled point from the centre
                a["center"] = round(max(-0.5, min(0.5, c)), 4)
            else:
                spread = None
            if self.hi[k] - self.lo[k] >= MIN_RANGE:          # only if the stick really moved
                a["min"] = round(max(-1.0, min(a["center"] - 0.05, self.lo[k])), 4)
                a["max"] = round(min(1.0, max(a["center"] + 0.05, self.hi[k])), 4)
            if spread is not None:
                # spread + jitter are raw units; the deadzone acts on the rescaled value, so scale
                # by the shorter half of the travel (the side where 1 raw unit counts most)
                span = max(0.05, min(a["max"] - a["center"], a["center"] - a["min"]))
                raw_dz = spread + self.jitter[k] + DEADZONE_MARGIN
                a["deadzone"] = round(min(MAX_DEADZONE, max(MIN_DEADZONE, raw_dz / span)), 3)
        for k in TRIGGERS:
            t = p.triggers[k]
            if self.trig_rest[k]:
                t["rest"] = round(max(0.0, min(0.5, self.trigger_rest(k))), 4)
            if self.tmax[k] - t["rest"] >= MIN_RANGE:
                t["max"] = round(max(t["rest"] + 0.1, self.tmax[k]), 4)
            if self.trig_rest[k]:
                span = max(0.1, t["max"] - t["rest"])
                t["deadzone"] = round(min(MAX_DEADZONE, max(0.02, (self.jitter[k] + DEADZONE_MARGIN) / span)), 3)
        return p
