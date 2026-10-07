"""DualShock 3 input via the SDL2 GameController API (pygame), polled in its own thread."""

import os
import sys

# Must be set before SDL initialises. Without this, SDL ignores the controller
# whenever its own (non-existent) window is unfocused - i.e. always, under Qt.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import threading
import time
from dataclasses import dataclass, field

import pygame   # works with either pygame or pygame-ce (install only ONE of them)
try:
    from pygame._sdl2 import controller as sdl_ctrl
except ImportError:          # no GameController API -> raw joystick fallback only
    sdl_ctrl = None


PAD_BUTTONS = ("cross", "circle", "square", "triangle", "l1", "r1", "l3", "r3",
               "select", "start", "ps", "up", "down", "left", "right")

# SDL normalises every pad to Xbox names; this maps them to DS3 names.
SDL_TO_DS3 = [
    ("cross", pygame.CONTROLLER_BUTTON_A),
    ("circle", pygame.CONTROLLER_BUTTON_B),
    ("square", pygame.CONTROLLER_BUTTON_X),
    ("triangle", pygame.CONTROLLER_BUTTON_Y),
    ("l1", pygame.CONTROLLER_BUTTON_LEFTSHOULDER),
    ("r1", pygame.CONTROLLER_BUTTON_RIGHTSHOULDER),
    ("l3", pygame.CONTROLLER_BUTTON_LEFTSTICK),
    ("r3", pygame.CONTROLLER_BUTTON_RIGHTSTICK),
    ("select", pygame.CONTROLLER_BUTTON_BACK),
    ("start", pygame.CONTROLLER_BUTTON_START),
    ("ps", pygame.CONTROLLER_BUTTON_GUIDE),
    ("up", pygame.CONTROLLER_BUTTON_DPAD_UP),
    ("down", pygame.CONTROLLER_BUTTON_DPAD_DOWN),
    ("left", pygame.CONTROLLER_BUTTON_DPAD_LEFT),
    ("right", pygame.CONTROLLER_BUTTON_DPAD_RIGHT),
]

# Fallback for a joystick SDL has no mapping for (raw XInput layout).
RAW_BUTTONS = {"cross": 0, "circle": 1, "square": 2, "triangle": 3, "l1": 4, "r1": 5,
               "select": 6, "start": 7, "l3": 8, "r3": 9, "ps": 10}


@dataclass(frozen=True)
class PadState:
    connected: bool = False
    name: str = ""
    mode: str = ""            # "SDL" (mapped) or "RAW" (fallback)
    lx: float = 0.0           # all axes -1..1, up/right positive
    ly: float = 0.0
    rx: float = 0.0
    ry: float = 0.0
    l2: float = 0.0           # 0..1
    r2: float = 0.0
    buttons: dict = field(default_factory=dict)

    def down(self, name):
        return bool(self.buttons.get(name))


class Gamepad:
    """Owns SDL in a background thread so SDL's event pump never touches Qt's."""

    def __init__(self, poll_hz=250):
        self._lock = threading.Lock()
        self._state = PadState()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._period = 1.0 / poll_hz
        self._ctrl = None
        self._joy = None
        self._name = ""
        self._next_scan = 0.0
        self.error = None
        self._thread = threading.Thread(target=self._run, name="gamepad", daemon=True)
        self._thread.start()
        self._ready.wait(3.0)

    def snapshot(self) -> PadState:
        with self._lock:
            return self._state

    def close(self):
        self._stop.set()
        self._thread.join(1.0)

    # ---- thread ----
    def _run(self):
        try:
            if sys.platform.startswith("linux") and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
                os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
            pygame.display.init()      # SDL needs the video subsystem to pump events
            pygame.joystick.init()
            if sdl_ctrl is not None:
                sdl_ctrl.init()
        except Exception as exc:       # noqa: BLE001
            self.error = f"SDL init failed: {exc}"
            self._ready.set()
            return
        self._hotplug = {pygame.JOYDEVICEADDED, pygame.JOYDEVICEREMOVED,
                         pygame.CONTROLLERDEVICEADDED, pygame.CONTROLLERDEVICEREMOVED}
        self._rescan()
        self._ready.set()
        while not self._stop.is_set():
            st = self._read()
            with self._lock:
                self._state = st
            time.sleep(self._period)
        self._close()
        pygame.quit()

    def _close(self):
        for dev in (self._ctrl, self._joy):
            try:
                if dev is not None:
                    dev.quit()
            except Exception:          # noqa: BLE001
                pass
        self._ctrl = self._joy = None
        self._name = ""

    def _rescan(self):
        self._close()
        for i in range(pygame.joystick.get_count()):
            try:
                if sdl_ctrl is not None and sdl_ctrl.is_controller(i):
                    self._ctrl = sdl_ctrl.Controller(i)
                    self._name = self._ctrl.name or "Controller"
                else:
                    self._joy = pygame.joystick.Joystick(i)
                    self._joy.init()
                    self._name = self._joy.get_name() or "Joystick"
                return
            except pygame.error:
                self._close()

    def _read(self) -> PadState:
        changed = False
        for ev in pygame.event.get():
            if ev.type in self._hotplug:
                changed = True
        now = time.monotonic()
        if changed or (self._ctrl is None and self._joy is None and now >= self._next_scan):
            self._next_scan = now + 1.0
            self._rescan()

        clamp = lambda v: max(-1.0, min(1.0, v))
        if self._ctrl is not None:
            c = self._ctrl
            try:
                if not c.attached():
                    raise pygame.error("detached")
                ax = lambda k: clamp(c.get_axis(k) / 32767.0)
                buttons = {n: bool(c.get_button(b)) for n, b in SDL_TO_DS3}
                return PadState(True, self._name, "SDL",
                                ax(pygame.CONTROLLER_AXIS_LEFTX), -ax(pygame.CONTROLLER_AXIS_LEFTY),
                                ax(pygame.CONTROLLER_AXIS_RIGHTX), -ax(pygame.CONTROLLER_AXIS_RIGHTY),
                                max(0.0, ax(pygame.CONTROLLER_AXIS_TRIGGERLEFT)),
                                max(0.0, ax(pygame.CONTROLLER_AXIS_TRIGGERRIGHT)),
                                buttons)
            except pygame.error:
                self._close()
        if self._joy is not None:
            j = self._joy
            try:
                nb, na = j.get_numbuttons(), j.get_numaxes()
                btn = lambda i: bool(j.get_button(i)) if i < nb else False
                ax = lambda i: clamp(j.get_axis(i)) if i < na else 0.0
                hat = j.get_hat(0) if j.get_numhats() else (0, 0)
                buttons = {n: btn(i) for n, i in RAW_BUTTONS.items()}
                buttons.update(up=hat[1] > 0, down=hat[1] < 0, left=hat[0] < 0, right=hat[0] > 0)
                return PadState(True, self._name, "RAW", ax(0), -ax(1), ax(2), -ax(3),
                                (ax(4) + 1) / 2 if na > 4 else 0.0,
                                (ax(5) + 1) / 2 if na > 5 else 0.0, buttons)
            except pygame.error:
                self._close()
        return PadState()
