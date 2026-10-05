#!/usr/bin/env python3
"""
Camosun ROV - topside control console
PySide6 UI + DualShock 3 input (SDL2 via pygame)

Control chain:  DualShock 3 -> this laptop (Windows) -> UDP -> Raspberry Pi -> STM32 -> thrusters

Run:
    py -m pip install PySide6                 # one-time (pygame-ce already installed)
    py rov_console.py --demo                  # no vehicle needed, simulated telemetry
    py rov_console.py --host 192.168.2.2      # real vehicle

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
WIRE CONTRACT  (proposed - the Pi side must match this)

Command packet  laptop -> Pi, UDP, CMD_PORT, 50 Hz, 16 bytes, little-endian
    struct format "<2sBBH6bbxH"
    0  2s   magic      b"RV"
    2  B    version    1
    3  B    flags      bit0 = armed
    4  H    seq        increments every packet, wraps at 65535
    6  6b   throttle   T1..T6, int8, -100..+100 percent
    12 b    cam_tilt   int8 degrees, TILT_MIN..TILT_MAX (0 = level, + = up)
                       sent even when disarmed; Pi maps it to servo PWM
    13 x    pad
    14 H    crc16      CRC-16/CCITT-FALSE over bytes 0..13
                       (Python: binascii.crc_hqx(pkt[:14], 0xFFFF))
    The Pi should zero all thrusters if no valid packet arrives for ~250 ms.

Telemetry  Pi -> laptop, UDP, TELEM_PORT, JSON object per datagram, any keys optional:
    {"depth_m": 12.4, "pressure_mbar": 2240, "water_c": 8.7, "internal_c": 41.6,
     "roll": 1.2, "pitch": -0.4, "yaw": 214.0, "voltage": 15.8, "current": 8.3,
     "leak": false, "ack": <last cmd seq received>, "rx_cmds": <total cmds received>}
-----------------------------------------------------------------------------
"""

import os
import sys

# Must be set before SDL initialises. Without this, SDL ignores the controller
# whenever its own (non-existent) window is unfocused - i.e. always, under Qt.
os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import argparse
import binascii
import html
import json
import math
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pygame   # works with either pygame or pygame-ce (install only ONE of them)
try:
    from pygame._sdl2 import controller as sdl_ctrl
except ImportError:          # no GameController API -> raw joystick fallback only
    sdl_ctrl = None

from PySide6.QtCore import Qt, QTimer, QRectF, QPointF
from PySide6.QtGui import (QAction, QColor, QFont, QKeySequence, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
                           QShortcut)
from PySide6.QtWidgets import (QApplication, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QMainWindow, QMessageBox, QPushButton,
                               QScrollArea, QSizePolicy, QTextEdit, QVBoxLayout,
                               QWidget)

APP_VERSION = "0.5.0"

# ============================================================================
# CONFIG - tune these on the bench
# ============================================================================
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

# ============================================================================
# THEME (from ROV Control Console mockup)
# ============================================================================
BG, PANEL, HEAD, WELL = "#0b0f14", "#0e131a", "#131a22", "#070a0e"
BORDER, BORDER2, GRID = "#1f2933", "#23303c", "#2c3a48"
TEXT, BRIGHT, MUTED, DIM, LABEL = "#d7e0ea", "#eaf2fa", "#5f7183", "#9fb0c2", "#8fa2b5"
ACCENT, WARN, DANGER, BLUE, OFF = "#35d0a5", "#ffd479", "#ff6b6e", "#7fb2ff", "#4d5d6d"

MONO = ["IBM Plex Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]
SANS = ["IBM Plex Sans", "Segoe UI", "DejaVu Sans", "sans-serif"]


def mono(px, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(MONO)
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def lab(text="", px=11, color=DIM, weight=QFont.Weight.Normal, align=None):
    w = QLabel(text)
    w.setFont(mono(px, weight))
    w.setStyleSheet(f"color: {color}; background: transparent;")
    if align is not None:
        w.setAlignment(align)
    return w


# ============================================================================
# GAMEPAD (DualShock 3 via SDL2 GameController API, polled in its own thread)
# ============================================================================
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


# ============================================================================
# LINK (UDP command out, JSON telemetry in)
# ============================================================================
CMD_STRUCT = struct.Struct("<2sBBH6bbx")   # 14 bytes, + 2-byte CRC = 16


def pack_command(seq, armed, throttles, tilt):
    body = CMD_STRUCT.pack(b"RV", 1, 1 if armed else 0, seq & 0xFFFF,
                           *[max(-100, min(100, int(t))) for t in throttles],
                           max(TILT_MIN, min(TILT_MAX, int(tilt))))
    return body + struct.pack("<H", binascii.crc_hqx(body, 0xFFFF))


class Link:
    def __init__(self, host, cmd_port, telem_port):
        self.label = f"{host} : {cmd_port}"
        self.addr = (host, cmd_port)
        self.seq = 0
        self.tx_count = 0
        self.rx_count = 0
        self.last_rx = 0.0
        self.rtt_ms = None
        self.loss_pct = None
        self.error = None
        self._sent = {}
        self._loss_ref = None
        self.tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tx.setblocking(False)
        self.rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx.setblocking(False)
        try:
            self.rx.bind(("0.0.0.0", telem_port))
        except OSError as exc:
            self.error = f"Cannot listen on UDP {telem_port}: {exc}"

    def up(self, now):
        return now - self.last_rx < LINK_TIMEOUT_S

    def send(self, armed, throttles, tilt):
        self.seq = (self.seq + 1) & 0xFFFF
        pkt = pack_command(self.seq, armed, throttles, tilt)
        self._sent[self.seq] = time.monotonic()
        self._sent.pop((self.seq - 200) & 0xFFFF, None)
        self._transmit(pkt)

    def _transmit(self, pkt):
        try:
            self.tx.sendto(pkt, self.addr)
            self.tx_count += 1
        except OSError as exc:
            self.error = f"Send failed: {exc}"

    def poll(self):
        latest = None
        while True:
            try:
                data, _ = self.rx.recvfrom(4096)
            except (BlockingIOError, ConnectionResetError):
                break
            except OSError:
                break
            try:
                msg = json.loads(data.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(msg, dict):
                latest = msg
                self._account(msg)
        return latest

    def _account(self, msg):
        now = time.monotonic()
        self.rx_count += 1
        self.last_rx = now
        ack = msg.get("ack")
        if isinstance(ack, int) and ack in self._sent:
            self.rtt_ms = (now - self._sent[ack]) * 1000.0
        rx_cmds = msg.get("rx_cmds")
        if isinstance(rx_cmds, int):
            if self._loss_ref is None:
                self._loss_ref = (now, self.tx_count, rx_cmds)
            elif now - self._loss_ref[0] >= 1.0:
                sent = self.tx_count - self._loss_ref[1]
                got = rx_cmds - self._loss_ref[2]
                if sent > 0:
                    self.loss_pct = max(0.0, min(100.0, 100.0 * (1 - got / sent)))
                self._loss_ref = (now, self.tx_count, rx_cmds)


class DemoLink(Link):
    """No network. A crude vehicle model answers every command so the UI is testable."""

    def __init__(self):
        super().__init__("127.0.0.1", 0, 0)
        self.label = "DEMO · simulated vehicle"
        self.error = None
        self.depth = 12.4
        self.heading = 214.0
        self.t0 = time.monotonic()
        self.temp = 39.5
        self._last = None

    def _transmit(self, pkt):
        self.tx_count += 1
        self._last = pkt

    def poll(self):
        if self._last is None:
            return None
        _, _, flags, seq, *rest = CMD_STRUCT.unpack(self._last[:14])
        thr = rest[:6]
        dt = 1.0 / RATE_HZ
        t = time.monotonic() - self.t0
        heave = (thr[4] + thr[5]) / 200.0
        yaw = (thr[0] - thr[1] + thr[2] - thr[3]) / 400.0
        self.depth = max(0.0, self.depth - heave * 0.6 * dt)
        self.heading = (self.heading + yaw * 35.0 * dt) % 360
        load = sum(abs(x) for x in thr) / 600.0
        self.temp += ((38.0 + 10.0 * load) - self.temp) * 0.002
        wob = lambda s, a: (math.sin(t * 0.7 + s) + 0.4 * math.sin(t * 1.9 + s * 2.3)) * a
        msg = {
            "depth_m": self.depth + wob(0.9, 0.02),
            "pressure_mbar": 1013.25 + self.depth * 100.5,
            "water_c": 8.7 + wob(2.2, 0.15),
            "internal_c": self.temp,
            "roll": wob(1.1, 3.0) + (thr[0] - thr[1]) / 40.0,
            "pitch": wob(2.7, 2.0) - (thr[0] + thr[1] - thr[2] - thr[3]) / 80.0,
            "yaw": self.heading,
            "voltage": 15.8 - load * 0.9,
            "current": 1.2 + load * 18.0,
            "leak": False,
            "ack": seq,
            "rx_cmds": self.tx_count,
        }
        self._account(msg)
        return msg


# ============================================================================
# PAINTED WIDGETS
# ============================================================================
class BipolarBar(QWidget):
    def __init__(self, height=18, knob=True):
        super().__init__()
        self.setFixedHeight(height)
        self.value, self.maxabs, self.color, self.knob = 0.0, 100.0, ACCENT, knob

    def set(self, value, color, maxabs=100.0):
        self.value, self.color, self.maxabs = value, color, maxabs
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(WELL))
        p.drawRoundedRect(r, 3, 3)
        cx = r.center().x()
        frac = max(-1.0, min(1.0, self.value / self.maxabs))
        half = (r.width() - 4) / 2
        inset = 2 if self.height() > 8 else 1
        fill = QRectF(cx, r.top() + inset, frac * half, r.height() - 2 * inset).normalized()
        c = QColor(self.color)
        c.setAlphaF(0.85)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(fill, 2, 2)
        p.setPen(QPen(QColor(GRID), 1))
        p.drawLine(QPointF(cx, r.top()), QPointF(cx, r.bottom()))
        if self.knob:
            kx = cx + frac * half
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BRIGHT))
            p.drawRoundedRect(QRectF(kx - 2, 0, 4, self.height()), 2, 2)


class TriggerBar(QWidget):
    """One-sided 0..1 fill used for the analog L2 / R2 triggers."""

    def __init__(self, color):
        super().__init__()
        self.setFixedHeight(10)
        self.value, self.color = 0.0, color

    def set(self, value):
        self.value = max(0.0, min(1.0, value))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(WELL))
        p.drawRoundedRect(r, 3, 3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawRoundedRect(QRectF(r.left() + 1, r.top() + 1, max(0.0, (r.width() - 2) * self.value), r.height() - 2), 2, 2)


class StickView(QWidget):
    def __init__(self, x_only=False):
        super().__init__()
        self.setFixedSize(112, 112)
        self.x = self.y = 0.0
        self.pressed = False
        self.x_only = x_only

    def set(self, x, y, pressed=False):
        self.x, self.y, self.pressed = x, y, pressed
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(WELL))
        p.drawRoundedRect(r, 4, 4)
        c = r.center()
        p.setPen(QPen(QColor("#1a2430"), 1))
        p.drawLine(QPointF(c.x(), r.top()), QPointF(c.x(), r.bottom()))
        p.drawLine(QPointF(r.left(), c.y()), QPointF(r.right(), c.y()))
        span = r.width() * 0.42
        dz = span * DEADZONE
        p.setPen(QPen(QColor(GRID), 1, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, dz, dz)
        if self.x_only:   # only X is used: draw the active track
            trk = QColor(ACCENT)
            trk.setAlpha(45)
            p.setPen(QPen(trk, 6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(c.x() - span, c.y()), QPointF(c.x() + span, c.y()))
        pos = QPointF(c.x() + self.x * span, c.y() - self.y * span)
        glow = QColor(ACCENT)
        glow.setAlpha(60)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow)
        p.drawEllipse(pos, 9, 9)
        p.setBrush(QColor(BRIGHT if self.pressed else ACCENT))
        p.drawEllipse(pos, 5, 5)


class VideoPane(QWidget):
    """Camera area with HUD. Video itself is a placeholder until the stream is wired in."""

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._bg = None
        self.s = dict(roll=0.0, pitch=0.0, heading=0.0, depth=None, armed=False,
                      arm_progress=0.0, gain=50, clock="--:--:--", depth_unit="m", tilt=0)

    def set_state(self, **kw):
        self.s.update(kw)
        self.update()

    def resizeEvent(self, e):
        self._bg = None
        super().resizeEvent(e)

    def _make_bg(self):
        w, h = self.width(), self.height()
        pm = QPixmap(w, h)
        pm.fill(QColor("#05070a"))
        p = QPainter(pm)
        g = QRadialGradient(QPointF(w * 0.5, h * 0.4), max(w, h) * 0.7)
        g.setColorAt(0.0, QColor("#123040"))
        g.setColorAt(0.45, QColor("#0a1a24"))
        g.setColorAt(1.0, QColor("#05090d"))
        p.fillRect(0, 0, w, h, g)
        p.setPen(QPen(QColor(255, 255, 255, 5), 1))
        for y in range(0, h, 3):
            p.drawLine(0, y, w, y)
        p.end()
        return pm

    def paintEvent(self, _):
        s = self.s
        w, h = self.width(), self.height()
        if self._bg is None:
            self._bg = self._make_bg()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.drawPixmap(0, 0, self._bg)
        cx, cy = w / 2, h / 2

        # placeholder camera
        dimc = QColor("#2c4653")
        p.setPen(QPen(dimc, 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(cx - 37, cy + 70, 74, 54), 8, 8)
        p.drawEllipse(QPointF(cx, cy + 97), 11, 11)
        p.setFont(mono(11))
        p.drawText(QRectF(0, cy + 132, w, 18), Qt.AlignmentFlag.AlignHCenter, "NO VIDEO SOURCE")
        p.setFont(mono(10))
        p.drawText(QRectF(0, cy + 150, w, 16), Qt.AlignmentFlag.AlignHCenter, "camera stream not connected")

        # crosshair
        ch = QColor(ACCENT)
        ch.setAlpha(90)
        p.setPen(QPen(ch, 1))
        p.drawLine(QPointF(cx - 60, cy), QPointF(cx + 60, cy))
        p.drawLine(QPointF(cx, cy - 60), QPointF(cx, cy + 60))
        ch.setAlpha(130)
        p.setPen(QPen(ch, 1))
        p.drawEllipse(QPointF(cx, cy), 17, 17)

        # arm state pill
        armed = s["armed"]
        pill = QRectF(22, 16, 108, 24)
        p.setPen(QPen(QColor(ACCENT if armed else "#3a4653"), 1))
        p.setBrush(QColor(10, 16, 22, 200))
        p.drawRoundedRect(pill, 3, 3)
        p.setFont(mono(11, QFont.Weight.Bold))
        p.setPen(QColor(ACCENT if armed else "#7c8b9c"))
        p.drawText(pill, Qt.AlignmentFlag.AlignCenter, "ARMED" if armed else "DISARMED")

        # clock
        p.setFont(mono(11))
        p.setPen(QColor("#7fd9c0"))
        p.drawText(QRectF(w - 222, 18, 200, 18), Qt.AlignmentFlag.AlignRight, f"{s['clock']} UTC")

        # attitude ball
        ar = QRectF(cx - 44, 14, 88, 88)
        p.save()
        path = QPainterPath()
        path.addEllipse(ar)
        p.setClipPath(path)
        p.translate(ar.center())
        p.rotate(-s["roll"])
        p.translate(0, max(-40.0, min(40.0, s["pitch"] * 1.4)))
        p.fillRect(QRectF(-120, -120, 240, 120), QColor("#1d4a63"))
        p.fillRect(QRectF(-120, 0, 240, 120), QColor("#3a2a16"))
        p.restore()
        ring = QColor(ACCENT)
        ring.setAlpha(90)
        p.setPen(QPen(ring, 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ar)
        p.setPen(QPen(QColor(WARN), 2))
        p.drawLine(QPointF(cx - 27, ar.center().y()), QPointF(cx + 27, ar.center().y()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(WARN))
        p.drawEllipse(ar.center(), 3, 3)
        p.setFont(mono(9))
        p.setPen(QColor(127, 217, 192, 190))
        p.drawText(QRectF(cx - 60, ar.bottom() + 3, 120, 14), Qt.AlignmentFlag.AlignHCenter, "ATTITUDE")

        # heading
        hdg = s["heading"] % 360
        cards = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
                 "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
        right = QRectF(w - 222, cy - 40, 200, 80)
        p.setFont(mono(10))
        p.setPen(QColor(127, 217, 192, 180))
        p.drawText(QRectF(right.left(), right.top(), 200, 14), Qt.AlignmentFlag.AlignRight, "HEADING")
        p.setFont(mono(40, QFont.Weight.Bold))
        p.setPen(QColor(BRIGHT))
        p.drawText(QRectF(right.left(), right.top() + 14, 200, 46), Qt.AlignmentFlag.AlignRight, f"{hdg:03.0f}")
        p.setFont(mono(11))
        p.setPen(QColor(234, 242, 250, 150))
        p.drawText(QRectF(right.left(), right.top() + 62, 200, 16), Qt.AlignmentFlag.AlignRight,
                   f"{cards[int(round(hdg / 22.5)) % 16]} · mag")

        # depth (bottom-left) and gain (bottom-right)
        p.setFont(mono(10))
        p.setPen(QColor(127, 217, 192, 180))
        p.drawText(QRectF(22, h - 64, 200, 14), Qt.AlignmentFlag.AlignLeft, "DEPTH")
        p.drawText(QRectF(w - 222, h - 64, 200, 14), Qt.AlignmentFlag.AlignRight, "THRUST GAIN")
        p.setFont(mono(26, QFont.Weight.Bold))
        p.setPen(QColor(BRIGHT))
        d = "--.--" if s["depth"] is None else f"{s['depth']:.2f}"
        p.drawText(QRectF(22, h - 50, 300, 34), Qt.AlignmentFlag.AlignLeft, f"{d} {s['depth_unit']}")
        p.drawText(QRectF(w - 222, h - 50, 200, 34), Qt.AlignmentFlag.AlignRight, f"{s['gain']}%")

        # camera tilt scale (left edge)
        sx, sh = 30.0, 160.0
        top = cy - sh / 2
        p.setPen(QPen(QColor(127, 217, 192, 90), 1))
        p.drawLine(QPointF(sx, top), QPointF(sx, top + sh))
        p.setFont(mono(9))
        for deg in range(TILT_MIN, TILT_MAX + 1, 15):
            y = cy - deg / max(abs(TILT_MIN), TILT_MAX) * sh / 2
            p.setPen(QPen(QColor(127, 217, 192, 90), 1))
            p.drawLine(QPointF(sx, y), QPointF(sx + (8 if deg == 0 else 4), y))
        ty = cy - s["tilt"] / max(abs(TILT_MIN), TILT_MAX) * sh / 2
        tri = QPainterPath()
        tri.moveTo(sx - 2, ty)
        tri.lineTo(sx - 10, ty - 5)
        tri.lineTo(sx - 10, ty + 5)
        tri.closeSubpath()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(WARN))
        p.drawPath(tri)
        p.setPen(QColor(127, 217, 192, 180))
        p.drawText(QRectF(sx - 8, top - 20, 120, 14), Qt.AlignmentFlag.AlignLeft, "CAM TILT")
        p.setFont(mono(12, QFont.Weight.Bold))
        p.setPen(QColor(BRIGHT))
        p.drawText(QRectF(sx + 12, ty - 9, 80, 18), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   f"{s['tilt']:+d}°")

        # hold-to-arm progress
        prog = s["arm_progress"]
        if prog > 0 and not armed:
            bar = QRectF(cx - 90, cy + 32, 180, 8)
            p.setPen(QPen(QColor(BORDER2), 1))
            p.setBrush(QColor(WELL))
            p.drawRoundedRect(bar, 3, 3)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * prog, bar.height()), 3, 3)
            p.setFont(mono(11, QFont.Weight.Bold))
            p.setPen(QColor(ACCENT))
            p.drawText(QRectF(0, cy + 44, w, 18), Qt.AlignmentFlag.AlignHCenter, "HOLD START TO ARM")


# ============================================================================
# COMPOSITE WIDGETS
# ============================================================================
class SectionHeader(QFrame):
    def __init__(self, title, right="", top_border=False):
        super().__init__()
        self.setObjectName("sechdr")
        self.setStyleSheet(f"QFrame#sechdr {{ background: {HEAD}; border-bottom: 1px solid {BORDER};"
                           + (f" border-top: 1px solid {BORDER};" if top_border else "") + " }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.addWidget(lab(title, 10, LABEL, QFont.Weight.Bold))
        lay.addStretch(1)
        if right:
            lay.addWidget(lab(right, 10, MUTED))


class ThrusterRow(QWidget):
    def __init__(self, name, role):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        top = QHBoxLayout()
        top.addWidget(lab(name, 11, DIM, QFont.Weight.DemiBold))
        top.addStretch(1)
        top.addWidget(lab(role, 10, MUTED))
        top.addStretch(1)
        self.val = lab("0%", 11, OFF, QFont.Weight.Bold, Qt.AlignmentFlag.AlignRight)
        self.val.setMinimumWidth(46)
        top.addWidget(self.val)
        v.addLayout(top)
        self.bar = BipolarBar(18)
        v.addWidget(self.bar)
        self._col = None

    def set(self, pct):
        col = OFF if pct == 0 else (WARN if abs(pct) > 80 else ACCENT)
        self.val.setText(f"{pct:+d}%" if pct else "0%")
        if col != self._col:
            self._col = col
            self.val.setStyleSheet(f"color: {col}; background: transparent;")
        self.bar.set(pct, col)


class Chip(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setFont(mono(10, QFont.Weight.DemiBold))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(20)
        self._on = None
        self.set(False)

    def set(self, on):
        if on == self._on:
            return
        self._on = on
        if on:
            self.setStyleSheet(f"color: #04120d; background: {ACCENT}; border: 1px solid {ACCENT}; border-radius: 3px;")
        else:
            self.setStyleSheet(f"color: {MUTED}; background: {HEAD}; border: 1px solid {BORDER2}; border-radius: 3px;")


class MetricCard(QFrame):
    def __init__(self, name, on_toggle):
        super().__init__()
        self.imperial = False
        self.setObjectName("metric")
        self.setStyleSheet(f"QFrame#metric {{ background: {PANEL}; }}")
        v = QVBoxLayout(self)
        v.setContentsMargins(12, 10, 12, 10)
        v.setSpacing(3)
        top = QHBoxLayout()
        top.addWidget(lab(name, 9, MUTED))
        top.addStretch(1)
        self.btn = QPushButton("SI")
        self.btn.setFont(mono(9, QFont.Weight.DemiBold))
        self.btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn.setFixedHeight(18)
        self.btn.clicked.connect(lambda: (self.set_imperial(not self.imperial), on_toggle()))
        self.btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        top.addWidget(self.btn)
        v.addLayout(top)
        self.val = QLabel("--")
        self.val.setFont(mono(24, QFont.Weight.Bold))
        v.addWidget(self.val)
        self.set_imperial(False)

    def set_imperial(self, imp):
        self.imperial = imp
        self.btn.setText("IMP" if imp else "SI")
        if imp:
            self.btn.setStyleSheet(f"QPushButton {{ padding: 0 6px; border: 1px solid #4a5a2e; border-radius: 3px; background: {HEAD}; color: #c9d67a; }}"
                                   f"QPushButton:hover {{ border-color: {ACCENT}; color: {BRIGHT}; }}")
        else:
            self.btn.setStyleSheet(f"QPushButton {{ padding: 0 6px; border: 1px solid {BORDER2}; border-radius: 3px; background: {HEAD}; color: #7c8b9c; }}"
                                   f"QPushButton:hover {{ border-color: {ACCENT}; color: {BRIGHT}; }}")

    def set(self, si, si_unit, imp, imp_unit, color=BRIGHT):
        v, u = (imp, imp_unit) if self.imperial else (si, si_unit)
        self.val.setText(f'<span style="color:{color}">{v}</span>'
                         f'<span style="font-size:11px; color:{MUTED}; font-weight:500"> {u}</span>')


class StatusRow(QFrame):
    def __init__(self, name):
        super().__init__()
        self.setStyleSheet(f"QFrame#row {{ background: #10161d; border: 1px solid {BORDER}; border-radius: 3px; }}")
        self.setObjectName("row")
        h = QHBoxLayout(self)
        h.setContentsMargins(9, 5, 9, 5)
        h.setSpacing(8)
        self.dot = QLabel()
        self.dot.setFixedSize(7, 7)
        h.addWidget(self.dot)
        h.addWidget(lab(name, 11, DIM), 1)
        self.val = lab("--", 11, TEXT, QFont.Weight.Bold)
        h.addWidget(self.val)
        self._last = None

    def set(self, value, color):
        if (value, color) == self._last:
            return
        self._last = (value, color)
        self.dot.setStyleSheet(f"background: {color}; border-radius: 3px;")
        self.val.setText(value)
        self.val.setStyleSheet(f"color: {color}; background: transparent;")


# ============================================================================
# MAIN WINDOW
# ============================================================================
class ConsoleWindow(QMainWindow):
    def __init__(self, args):
        super().__init__()
        self.setWindowTitle("Camosun ROV — Control Console")
        self.resize(1440, 900)
        self.setMinimumSize(1200, 760)

        self.demo = args.demo
        self.link = DemoLink() if args.demo else Link(args.host, args.cmd_port, args.telem_port)
        self.pad = Gamepad()

        self.armed = False
        self.tilt = 0
        self.gain_idx = DEFAULT_GAIN_INDEX
        self.throttles = [0] * 6
        self.tel = {}
        self.prev_buttons = {}
        self.arm_hold_start = None
        self.repeat_at = {}
        self.was_connected = False
        self.was_linked = False
        self.temp_warned = False
        self.leak_alarmed = False
        self.temp_warned = False
        self.leak_alarmed = False
        self.diag = args.diag
        self._t_last = None
        self._dt_max = self._work_max = 0.0
        self._diag_at = time.monotonic() + 5

        self._build_ui()
        self.log("SYS", f"Console v{APP_VERSION} started" + (" in DEMO mode" if self.demo else ""), BLUE)
        if self.pad.error:
            self.log("WARN", self.pad.error, WARN)
        if self.link.error:
            self.log("WARN", self.link.error, WARN)

        QShortcut(QKeySequence(Qt.Key.Key_Space), self, activated=lambda: self.estop("keyboard SPACE"))

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(int(1000 / RATE_HZ))
        self.ui_timer = QTimer(self)
        self.ui_timer.timeout.connect(self.refresh_ui)
        self.ui_timer.start(33)          # ~30 Hz is plenty for the display

    # ---------------- UI construction ----------------
    def _build_ui(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget#central {{ background: {BG}; }}
            QMenuBar {{ background: #141a22; color: {DIM}; border-bottom: 1px solid {BORDER}; padding: 2px 4px; }}
            QMenuBar::item {{ padding: 3px 9px; border-radius: 3px; background: transparent; }}
            QMenuBar::item:selected {{ background: {BORDER}; color: {BRIGHT}; }}
            QMenu {{ background: {HEAD}; color: {TEXT}; border: 1px solid {BORDER2}; }}
            QMenu::item {{ padding: 5px 18px; }}
            QMenu::item:selected {{ background: {BORDER}; }}
            QStatusBar {{ background: #10151c; border-top: 1px solid {BORDER}; color: {MUTED}; }}
            QStatusBar::item {{ border: none; }}
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ background: {PANEL}; width: 8px; }}
            QScrollBar::handle:vertical {{ background: {BORDER2}; border-radius: 4px; }}
            QToolTip {{ background: {HEAD}; color: {TEXT}; border: 1px solid {BORDER2}; }}
        """)
        f = QFont()
        f.setFamilies(SANS)
        f.setPixelSize(13)
        self.setFont(f)

        self._build_menu()

        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_toolbar())

        body = QHBoxLayout()
        body.setSpacing(0)
        body.addWidget(self._build_left())
        body.addWidget(self._build_center(), 1)
        body.addWidget(self._build_right())
        root.addLayout(body, 1)
        self.setCentralWidget(central)
        self._build_statusbar()

    def _build_menu(self):
        mb = self.menuBar()
        title = lab("SUBSEA ROV CONSOLE", 11, ACCENT, QFont.Weight.Bold)
        title.setContentsMargins(8, 0, 12, 0)
        mb.setCornerWidget(title, Qt.Corner.TopLeftCorner)
        m = mb.addMenu("File")
        m.addAction("Quit", self.close)
        m = mb.addMenu("Vehicle")
        a = QAction("Arm / Disarm", self)
        a.triggered.connect(self.toggle_arm_click)
        m.addAction(a)
        a = QAction("E-STOP\tSpace", self)
        a.triggered.connect(lambda: self.estop("menu"))
        m.addAction(a)
        m = mb.addMenu("Help")
        m.addAction("Controller map", self.show_controller_map)

    def _build_toolbar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"QFrame#tb {{ background: #10151c; border-bottom: 1px solid {BORDER}; }}")
        bar.setObjectName("tb")
        h = QHBoxLayout(bar)
        h.setContentsMargins(12, 0, 12, 0)
        h.setSpacing(10)

        pill_css = f"QFrame#pill {{ border: 1px solid {BORDER2}; border-radius: 4px; background: {HEAD}; }}"
        link = QFrame()
        link.setObjectName("pill")
        link.setStyleSheet(pill_css)
        lh = QHBoxLayout(link)
        lh.setContentsMargins(11, 5, 11, 5)
        lh.setSpacing(8)
        self.link_dot = QLabel()
        self.link_dot.setFixedSize(8, 8)
        lh.addWidget(self.link_dot)
        self.link_lbl = lab("LINK DOWN", 11, TEXT, QFont.Weight.DemiBold)
        lh.addWidget(self.link_lbl)
        lh.addWidget(lab(self.link.label, 11, MUTED))
        h.addWidget(link)

        stats = QFrame()
        stats.setObjectName("pill")
        stats.setStyleSheet(pill_css)
        sh = QHBoxLayout(stats)
        sh.setContentsMargins(11, 5, 11, 5)
        self.stats_lbl = QLabel()
        self.stats_lbl.setFont(mono(11))
        sh.addWidget(self.stats_lbl)
        h.addWidget(stats)

        h.addStretch(1)
        self.pad_lbl = QLabel()
        self.pad_lbl.setFont(mono(11))
        h.addWidget(self.pad_lbl)

        self.arm_btn = QPushButton("DISARMED")
        self.arm_btn.setFont(mono(12, QFont.Weight.Bold))
        self.arm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.arm_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.arm_btn.setMinimumWidth(150)
        self.arm_btn.clicked.connect(self.toggle_arm_click)
        h.addWidget(self.arm_btn)
        self._arm_style = None

        es = QPushButton("E-STOP")
        es.setFont(mono(12, QFont.Weight.Bold))
        es.setCursor(Qt.CursorShape.PointingHandCursor)
        es.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        es.setStyleSheet("QPushButton { padding: 7px 18px; border-radius: 4px; border: 1px solid #7f2b2e;"
                         " background: qlineargradient(y1:0, y2:1, stop:0 #3a1416, stop:1 #2a0f11); color: #ff6b6e; }"
                         " QPushButton:hover { background: #57191c; color: #fff; }")
        es.clicked.connect(lambda: self.estop("console button"))
        h.addWidget(es)
        return bar

    def _panel(self, width, side):
        f = QFrame()
        f.setFixedWidth(width)
        f.setObjectName("panel")
        f.setStyleSheet(f"QFrame#panel {{ background: {PANEL}; border-{side}: 1px solid {BORDER}; }}")
        v = QVBoxLayout(f)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        return f, v

    def _build_left(self):
        outer, ov = self._panel(300, "right")
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        v = QVBoxLayout(inner)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        v.addWidget(SectionHeader("THRUSTER OUTPUT", "TX → PI"))
        tw = QWidget()
        tv = QVBoxLayout(tw)
        tv.setContentsMargins(12, 10, 12, 8)
        tv.setSpacing(8)
        self.thr_rows = []
        for name, role, _, _ in THRUSTERS:
            r = ThrusterRow(name, role)
            self.thr_rows.append(r)
            tv.addWidget(r)
        gain = QHBoxLayout()
        gain.addWidget(lab("GAIN", 11, DIM))
        self.gain_lbl = lab("50%", 11, ACCENT, QFont.Weight.Bold)
        gain.addWidget(self.gain_lbl)
        gain.addStretch(1)
        gain.addWidget(lab("L1 ▼  R1 ▲", 10, MUTED))
        tv.addLayout(gain)
        v.addWidget(tw)

        v.addWidget(SectionHeader("STICK INPUT", "DUALSHOCK 3", top_border=True))
        sw = QWidget()
        sg = QGridLayout(sw)
        sg.setContentsMargins(12, 10, 12, 10)
        sg.setHorizontalSpacing(12)
        sg.setVerticalSpacing(4)
        self.stick_l, self.stick_r = StickView(), StickView(x_only=True)
        sg.addWidget(self.stick_l, 0, 0, Qt.AlignmentFlag.AlignHCenter)
        sg.addWidget(self.stick_r, 0, 1, Qt.AlignmentFlag.AlignHCenter)
        sg.addWidget(lab("L · FWD/BACK + SIDE", 9, MUTED, align=Qt.AlignmentFlag.AlignHCenter), 1, 0)
        sg.addWidget(lab("R · ROTATE (YAW)", 9, MUTED, align=Qt.AlignmentFlag.AlignHCenter), 1, 1)
        v.addWidget(sw)

        trw = QWidget()
        tg = QGridLayout(trw)
        tg.setContentsMargins(12, 0, 12, 10)
        tg.setHorizontalSpacing(8)
        tg.setVerticalSpacing(4)
        self.l2_bar, self.r2_bar = TriggerBar(BLUE), TriggerBar(ACCENT)
        tg.addWidget(lab("L2 · DESCEND", 9, MUTED), 0, 0)
        tg.addWidget(lab("R2 · ASCEND", 9, MUTED), 0, 1)
        tg.addWidget(self.l2_bar, 1, 0)
        tg.addWidget(self.r2_bar, 1, 1)
        v.addWidget(trw)

        cw = QWidget()
        cg = QGridLayout(cw)
        cg.setContentsMargins(12, 0, 12, 12)
        cg.setSpacing(4)
        self.chips = {}
        chip_layout = [("✕", "cross"), ("○", "circle"), ("□", "square"), ("△", "triangle"),
                       ("L1", "l1"), ("R1", "r1"), ("L2", "l2"), ("R2", "r2"),
                       ("SEL", "select"), ("START", "start"), ("PS", "ps"), ("↑↓", "dpad")]
        for i, (text, key) in enumerate(chip_layout):
            c = Chip(text)
            self.chips[key] = c
            cg.addWidget(c, i // 4, i % 4)
        v.addWidget(cw)

        v.addWidget(SectionHeader("CAMERA TILT", "D-PAD", top_border=True))
        cw2 = QWidget()
        cv = QVBoxLayout(cw2)
        cv.setContentsMargins(12, 10, 12, 10)
        cv.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(lab("SERVO ANGLE", 11, DIM))
        top.addStretch(1)
        self.tilt_lbl = lab("+0°", 22, WARN, QFont.Weight.Bold)
        top.addWidget(self.tilt_lbl)
        cv.addLayout(top)
        self.tilt_bar = BipolarBar(18)
        cv.addWidget(self.tilt_bar)
        ends = QHBoxLayout()
        ends.addWidget(lab(f"DOWN {TILT_MIN}°", 9, MUTED))
        ends.addStretch(1)
        ends.addWidget(lab(f"UP +{TILT_MAX}°", 9, MUTED))
        cv.addLayout(ends)
        cv.addWidget(lab(f"D-pad ↑↓ · {TILT_STEP}° per step · hold to repeat", 10, MUTED))
        v.addWidget(cw2)

        v.addStretch(1)
        foot = QFrame()
        foot.setObjectName("foot")
        foot.setStyleSheet(f"QFrame#foot {{ background: #0a0e13; border-top: 1px solid {BORDER}; }}")
        fv = QVBoxLayout(foot)
        fv.setContentsMargins(12, 8, 12, 8)
        fv.setSpacing(2)
        fv.addWidget(lab(f"PACKET  cmd_v1 · 16 B · {RATE_HZ} Hz", 10, MUTED))
        fv.addWidget(lab("PAYLOAD 6×int8 throttle + int8 cam tilt", 10, MUTED))
        v.addWidget(foot)

        scroll.setWidget(inner)
        ov.addWidget(scroll)
        return outer

    def _build_center(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        self.video = VideoPane()
        v.addWidget(self.video, 1)

        logf = QFrame()
        logf.setFixedHeight(130)
        logf.setObjectName("logf")
        logf.setStyleSheet(f"QFrame#logf {{ background: {PANEL}; border-top: 1px solid {BORDER}; }}")
        lv = QVBoxLayout(logf)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)
        hdr = QFrame()
        hdr.setObjectName("loghdr")
        hdr.setStyleSheet(f"QFrame#loghdr {{ border-bottom: 1px solid {BORDER}; }}")
        hh = QHBoxLayout(hdr)
        hh.setContentsMargins(12, 6, 12, 6)
        hh.addWidget(lab("EVENT LOG", 10, LABEL, QFont.Weight.Bold))
        hh.addWidget(lab(f"· command stream {RATE_HZ} Hz", 10, MUTED))
        hh.addStretch(1)
        lv.addWidget(hdr)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(mono(11))
        self.log_view.document().setMaximumBlockCount(300)
        self.log_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log_view.setStyleSheet(f"QTextEdit {{ background: {PANEL}; border: none; color: {DIM}; padding: 4px 8px; }}")
        lv.addWidget(self.log_view)
        v.addWidget(logf)
        return w

    def _build_right(self):
        outer, v = self._panel(296, "left")
        v.addWidget(SectionHeader("TELEMETRY", "RX ← PI"))
        grid = QFrame()
        grid.setObjectName("mgrid")
        grid.setStyleSheet(f"QFrame#mgrid {{ background: {BORDER}; }}")
        g = QGridLayout(grid)
        g.setContentsMargins(0, 0, 0, 1)
        g.setSpacing(1)
        self.metrics = {}
        for i, (key, name) in enumerate([("depth", "DEPTH"), ("pressure", "PRESSURE"),
                                         ("water", "WATER TEMP"), ("internal", "INTERNAL TEMP")]):
            card = MetricCard(name, self.refresh_units)
            self.metrics[key] = card
            g.addWidget(card, i // 2, i % 2)
        v.addWidget(grid)

        imu = QWidget()
        iv = QVBoxLayout(imu)
        iv.setContentsMargins(12, 12, 12, 12)
        iv.setSpacing(8)
        iv.addWidget(lab("IMU ATTITUDE", 10, LABEL, QFont.Weight.Bold))
        self.imu_rows = {}
        for key in ("ROLL", "PITCH", "YAW"):
            top = QHBoxLayout()
            top.addWidget(lab(key, 11, DIM))
            top.addStretch(1)
            val = lab("--", 11, BRIGHT, QFont.Weight.Bold)
            top.addWidget(val)
            iv.addLayout(top)
            bar = BipolarBar(6, knob=False)
            iv.addWidget(bar)
            self.imu_rows[key] = (val, bar)
        v.addWidget(imu)
        v.addWidget(self._hline())

        pw = QWidget()
        pv = QVBoxLayout(pw)
        pv.setContentsMargins(12, 12, 12, 12)
        pv.setSpacing(6)
        pv.addWidget(lab("POWER", 10, LABEL, QFont.Weight.Bold))
        pv.addWidget(lab("BATTERY", 9, MUTED))
        self.volt_lbl = QLabel("--")
        self.volt_lbl.setFont(mono(32, QFont.Weight.Bold))
        pv.addWidget(self.volt_lbl)
        self.soc_bar = LevelBarSOC()
        pv.addWidget(self.soc_bar)
        row = QHBoxLayout()
        self.soc_lbl = lab("SOC est. --", 10, MUTED)
        self.amp_lbl = lab("-- A", 10, MUTED)
        row.addWidget(self.soc_lbl)
        row.addStretch(1)
        row.addWidget(self.amp_lbl)
        pv.addLayout(row)
        v.addWidget(pw)
        v.addWidget(self._hline())

        sw = QWidget()
        sv = QVBoxLayout(sw)
        sv.setContentsMargins(12, 12, 12, 12)
        sv.setSpacing(6)
        sv.addWidget(lab("SYSTEM STATUS", 10, LABEL, QFont.Weight.Bold))
        self.st_leak = StatusRow("Leak sensor")
        self.st_link = StatusRow("Telemetry link")
        self.st_pad = StatusRow("Controller")
        self.st_cmd = StatusRow("Command stream")
        for r in (self.st_leak, self.st_link, self.st_pad, self.st_cmd):
            sv.addWidget(r)
        v.addWidget(sw)
        v.addStretch(1)
        return outer

    def _hline(self):
        f = QFrame()
        f.setFixedHeight(1)
        f.setObjectName("hline")
        f.setStyleSheet(f"QFrame#hline {{ background: {BORDER}; }}")
        return f

    def _build_statusbar(self):
        sb = self.statusBar()
        sb.setFixedHeight(24)
        sb.setSizeGripEnabled(False)
        self.msg_lbl = lab("", 10, DIM)
        self.msg_lbl.setContentsMargins(10, 0, 0, 0)
        sb.addWidget(self.msg_lbl, 1)
        self.tx_lbl = lab("", 10, MUTED)
        self.rx_lbl = lab("", 10, MUTED)
        for w in (self.tx_lbl, self.rx_lbl, lab(f"v{APP_VERSION}", 10, MUTED)):
            sb.addPermanentWidget(w)

    # ---------------- actions ----------------
    def log(self, tag, msg, color=ACCENT):
        t = datetime.now(timezone.utc).strftime("%H:%M:%S")
        tagp = html.escape(tag).ljust(5).replace(" ", "&nbsp;")
        self.log_view.append(f'<span style="color:#4d5d6d">{t}</span>&nbsp;&nbsp;'
                             f'<span style="color:{color}; font-weight:600">{tagp}</span>&nbsp;'
                             f'<span style="color:{DIM}">{html.escape(msg)}</span>')

    def try_arm(self, source):
        now = time.monotonic()
        pad = self.pad.snapshot()
        if pad.connected and max(abs(pad.lx), abs(pad.ly), abs(pad.rx), abs(pad.ry)) > 0.15:
            self.log("DENY", "Arm refused — centre both sticks first", WARN)
            return
        if pad.connected and max(pad.l2, pad.r2) > 0.15:
            self.log("DENY", "Arm refused — release L2 and R2 first", WARN)
            return
        if REQUIRE_LINK_TO_ARM and not self.link.up(now):
            self.log("DENY", "Arm refused — no telemetry link to the Pi", WARN)
            return
        self.armed = True
        self.log("ARM", f"Thrusters ARMED ({source})", ACCENT)

    def disarm(self, reason, tag="ARM", color=MUTED):
        if self.armed:
            self.armed = False
            self.log(tag, f"Thrusters disarmed — {reason}", color)

    def estop(self, source):
        was = self.armed
        self.armed = False
        self.arm_hold_start = None
        self.throttles = [0] * 6
        self.link.send(False, self.throttles, self.tilt)   # send zero frame immediately
        self.log("ESTOP", f"E-STOP from {source}" + ("" if was else " (already disarmed)"), DANGER)

    def toggle_arm_click(self):
        if self.armed:
            self.disarm("console button")
        else:
            self.try_arm("console button")

    def refresh_units(self):
        self._update_metrics()

    def show_controller_map(self):
        QMessageBox.information(self, "DualShock 3 controls", (
            "Left stick — forward/back + side to side\n"
            "Right stick left/right — rotate (yaw)\n"
            "L2 — descend · R2 — ascend (analog)\n"
            "D-pad ↑ / ↓ — camera tilt\n\n"
            f"START (hold {ARM_HOLD_S:.0f} s) — arm\n"
            "START (tap while armed) — disarm\n"
            "SELECT or PS — E-STOP\n"
            "L1 / R1 — thrust gain down / up\n"
            "△ — toggle SI / imperial units\n"
            "□ — operator mark in log\n\n"
            "Keyboard SPACE — E-STOP"))

    # ---------------- control loop ----------------
    def tick(self):
        now = time.monotonic()
        pad = self.pad.snapshot()
        self._handle_pad(pad, now)
        self.throttles = self._mix(pad) if (self.armed and pad.connected) else [0] * 6
        self.link.send(self.armed, self.throttles, self.tilt)
        tel = self.link.poll()
        if tel:
            self.tel.update(tel)
        self._failsafes(now)

    def refresh_ui(self):
        self._refresh(self.pad.snapshot(), time.monotonic())

    def _handle_pad(self, pad, now):
        if pad.connected and not self.was_connected:
            self.log("PAD", f"Controller connected — {pad.name} [{pad.mode}]", ACCENT)
        if not pad.connected and self.was_connected:
            self.log("PAD", "Controller disconnected", WARN)
            self.disarm("controller lost", "FAIL", WARN)
            self.arm_hold_start = None
        self.was_connected = pad.connected
        if not pad.connected:
            self.prev_buttons = {}
            return

        prev = self.prev_buttons
        pressed = lambda b: pad.down(b) and not prev.get(b)

        if pressed("select") or pressed("ps"):
            self.estop("controller " + ("SELECT" if pad.down("select") else "PS"))

        if pressed("start"):
            if self.armed:
                self.disarm("START")
            else:
                self.arm_hold_start = now
        if not pad.down("start"):
            self.arm_hold_start = None
        elif self.arm_hold_start is not None and not self.armed and now - self.arm_hold_start >= ARM_HOLD_S:
            self.arm_hold_start = None
            self.try_arm("START held")

        for b, d in (("up", 1), ("down", -1)):
            if pressed(b):
                self._step_tilt(d)
                self.repeat_at[b] = now + 0.40
            elif pad.down(b) and now >= self.repeat_at.get(b, math.inf):
                self._step_tilt(d)
                self.repeat_at[b] = now + 0.12

        if pressed("l1") and self.gain_idx > 0:
            self.gain_idx -= 1
            self.log("CMD", f"Thrust gain {GAIN_STEPS[self.gain_idx]}%", ACCENT)
        if pressed("r1") and self.gain_idx < len(GAIN_STEPS) - 1:
            self.gain_idx += 1
            self.log("CMD", f"Thrust gain {GAIN_STEPS[self.gain_idx]}%", ACCENT)
        if pressed("triangle"):
            imp = not all(c.imperial for c in self.metrics.values())
            for c in self.metrics.values():
                c.set_imperial(imp)
            self._update_metrics()
        if pressed("square"):
            d = self.tel.get("depth_m")
            self.log("MARK", "Operator mark" + (f" @ {d:.2f} m" if isinstance(d, (int, float)) else ""), BLUE)

        self.prev_buttons = dict(pad.buttons)

    def _step_tilt(self, d):
        new = max(TILT_MIN, min(TILT_MAX, self.tilt + d * TILT_STEP))
        if new != self.tilt:
            self.tilt = new
            self.log("CAM", f"Camera tilt {new:+d}°", BLUE)

    @staticmethod
    def _shape(v):
        a = abs(v)
        if a < DEADZONE:
            return 0.0
        a = (a - DEADZONE) / (1 - DEADZONE)
        a = (1 - EXPO) * a + EXPO * a ** 3
        return math.copysign(a, v)

    def _mix(self, pad):
        trig = lambda v: 0.0 if v < TRIGGER_DEADZONE else (v - TRIGGER_DEADZONE) / (1 - TRIGGER_DEADZONE)
        heave = trig(pad.r2) - trig(pad.l2)        # R2 up, L2 down
        axes = (self._shape(pad.ly), self._shape(pad.lx), heave, self._shape(pad.rx))
        raw = [sum(c * a for c, a in zip(coef, axes)) for _, _, _, coef in THRUSTERS]
        out = [0.0] * len(raw)
        for grp in ("H", "V"):
            idx = [i for i, t in enumerate(THRUSTERS) if t[2] == grp]
            peak = max([1.0] + [abs(raw[i]) for i in idx])
            for i in idx:
                out[i] = raw[i] / peak
        g = GAIN_STEPS[self.gain_idx]
        return [int(round(x * g)) for x in out]

    def _failsafes(self, now):
        linked = self.link.up(now)
        if linked and not self.was_linked:
            self.log("LINK", "Telemetry received — link up", ACCENT)
        if not linked and self.was_linked:
            self.log("LINK", "Telemetry lost", DANGER)
            self.disarm("link lost", "FAIL", DANGER)
        self.was_linked = linked

        it = self.tel.get("internal_c")
        if isinstance(it, (int, float)):
            if it > 45 and not self.temp_warned:
                self.temp_warned = True
                self.log("WARN", f"Internal temp high — {it:.1f} °C", WARN)
            elif it < 43:
                self.temp_warned = False
        leak = bool(self.tel.get("leak"))
        if leak and not self.leak_alarmed:
            self.log("ALARM", "LEAK DETECTED — surface the vehicle", DANGER)
        self.leak_alarmed = leak

    # ---------------- UI refresh ----------------
    def _num(self, key):
        v = self.tel.get(key)
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

    def _update_metrics(self):
        d, p, wt, it = (self._num(k) for k in ("depth_m", "pressure_mbar", "water_c", "internal_c"))
        f = lambda v, fmt: "--" if v is None else format(v, fmt)
        c2f = lambda c: None if c is None else c * 9 / 5 + 32
        self.metrics["depth"].set(f(d, ".2f"), "m", f(None if d is None else d * 3.28084, ".1f"), "ft")
        self.metrics["pressure"].set(f(p, ".0f"), "mbar", f(None if p is None else p * 0.0145038, ".1f"), "psi")
        self.metrics["water"].set(f(wt, ".1f"), "°C", f(c2f(wt), ".1f"), "°F")
        self.metrics["internal"].set(f(it, ".1f"), "°C", f(c2f(it), ".1f"), "°F",
                                     WARN if (it is not None and it > 45) else BRIGHT)

    def _refresh(self, pad, now):
        linked = self.link.up(now)

        # toolbar
        lc = ACCENT if linked else "#e5484d"
        self.link_dot.setStyleSheet(f"background: {lc}; border-radius: 4px;")
        self.link_lbl.setText("LINK UP" if linked else "LINK DOWN")
        rtt = "--" if self.link.rtt_ms is None or not linked else f"{self.link.rtt_ms:.1f}"
        loss = "--" if self.link.loss_pct is None or not linked else f"{self.link.loss_pct:.1f}"
        sep = f'<span style="color:{BORDER2}">&nbsp;│&nbsp;</span>'
        self.stats_lbl.setText(
            f'<span style="color:{MUTED}">RATE </span><b style="color:{ACCENT}">{RATE_HZ}</b><span style="color:{MUTED}"> Hz</span>{sep}'
            f'<span style="color:{MUTED}">RTT </span><b style="color:{TEXT}">{rtt}</b><span style="color:{MUTED}"> ms</span>{sep}'
            f'<span style="color:{MUTED}">LOSS </span><b style="color:{TEXT}">{loss}</b><span style="color:{MUTED}"> %</span>')
        if pad.connected:
            name = pad.name if len(pad.name) <= 22 else pad.name[:21] + "…"
            self.pad_lbl.setText(f'<span style="color:#7c8b9c">GAMEPAD </span>'
                                 f'<b style="color:{ACCENT}">{html.escape(name)} OK</b>'
                                 + ("" if pad.mode == "SDL" else f'<span style="color:{WARN}"> RAW</span>'))
        else:
            self.pad_lbl.setText(f'<span style="color:#7c8b9c">GAMEPAD </span><b style="color:{DANGER}">NOT FOUND</b>')

        hold = 0.0
        if self.arm_hold_start is not None and not self.armed:
            hold = min(1.0, (now - self.arm_hold_start) / ARM_HOLD_S)
        style = ("armed" if self.armed else "disarmed")
        if style != self._arm_style:
            self._arm_style = style
            if self.armed:
                self.arm_btn.setStyleSheet(f"QPushButton {{ padding: 7px 18px; border-radius: 4px; border: 1px solid #2a6f5c;"
                                           f" background: qlineargradient(y1:0, y2:1, stop:0 #123a30, stop:1 #0e2c25); color: {ACCENT}; }}")
            else:
                self.arm_btn.setStyleSheet("QPushButton { padding: 7px 18px; border-radius: 4px; border: 1px solid #3a4653;"
                                           " background: qlineargradient(y1:0, y2:1, stop:0 #1b222b, stop:1 #151b23); color: #7c8b9c; }")
        self.arm_btn.setText("ARMED" if self.armed else (f"ARMING {hold * 100:.0f}%" if hold > 0 else "DISARMED"))

        # left panel
        for row, pct in zip(self.thr_rows, self.throttles):
            row.set(pct)
        self.gain_lbl.setText(f"{GAIN_STEPS[self.gain_idx]}%")
        self.stick_l.set(pad.lx, pad.ly, pad.down("l3"))
        self.stick_r.set(pad.rx, 0.0, pad.down("r3"))
        self.l2_bar.set(pad.l2)
        self.r2_bar.set(pad.r2)
        for key, chip in self.chips.items():
            if key == "l2":
                chip.set(pad.l2 > 0.5)
            elif key == "r2":
                chip.set(pad.r2 > 0.5)
            elif key == "dpad":
                chip.set(pad.down("up") or pad.down("down") or pad.down("left") or pad.down("right"))
            else:
                chip.set(pad.down(key))
        self.tilt_lbl.setText(f"{self.tilt:+d}°")
        self.tilt_bar.set(self.tilt, WARN, max(abs(TILT_MIN), TILT_MAX))

        # telemetry
        self._update_metrics()
        roll, pitch, yaw = self._num("roll"), self._num("pitch"), self._num("yaw")
        for key, val, mx in (("ROLL", roll, 45), ("PITCH", pitch, 45),
                             ("YAW", None if yaw is None else ((yaw + 180) % 360) - 180, 180)):
            lbl, bar = self.imu_rows[key]
            lbl.setText("--" if val is None else f"{val:+.1f}°")
            bar.set(val or 0.0, ACCENT, mx)
        v, amps = self._num("voltage"), self._num("current")
        self.volt_lbl.setText(f'<span style="color:{BRIGHT}">{"--" if v is None else f"{v:.2f}"}</span>'
                              f'<span style="font-size:12px; color:{MUTED}; font-weight:500"> V</span>')
        soc = None if v is None else max(0, min(100, round((v - 13.2) / (16.8 - 13.2) * 100)))  # 4S Li-ion guess
        self.soc_bar.set(soc or 0)
        self.soc_lbl.setText("SOC est. --" if soc is None else f"SOC est. {soc}%")
        self.amp_lbl.setText("-- A" if amps is None else f"{amps:.1f} A")

        leak = self.tel.get("leak")
        if not linked or leak is None:
            self.st_leak.set("NO DATA", MUTED)
        else:
            self.st_leak.set("LEAK" if leak else "DRY", DANGER if leak else ACCENT)
        self.st_link.set("UP" if linked else "DOWN", ACCENT if linked else DANGER)
        self.st_pad.set(("OK" if pad.mode == "SDL" else "RAW") if pad.connected else "MISSING",
                        (ACCENT if pad.mode == "SDL" else WARN) if pad.connected else DANGER)
        self.st_cmd.set(f"{RATE_HZ} Hz", TEXT)

        # video HUD
        imp = self.metrics["depth"].imperial
        d = self._num("depth_m")
        self.video.set_state(
            roll=roll or 0.0, pitch=pitch or 0.0, heading=yaw or 0.0,
            depth=None if d is None else (d * 3.28084 if imp else d), depth_unit="ft" if imp else "m",
            armed=self.armed, arm_progress=hold, gain=GAIN_STEPS[self.gain_idx], tilt=self.tilt,
            clock=datetime.now(timezone.utc).strftime("%H:%M:%S"))

        # status bar
        if self.armed:
            self.msg_lbl.setText("Thrusters armed — streaming control frames")
        elif not pad.connected:
            self.msg_lbl.setText("Connect the DualShock 3 to drive — see Help ▸ Controller map")
        else:
            self.msg_lbl.setText(f"Thrusters disarmed — hold START {ARM_HOLD_S:.0f} s to arm")
        self.tx_lbl.setText(f"TX {self.link.tx_count:,} pkt   │")
        self.rx_lbl.setText(f"RX {self.link.rx_count:,} pkt   │")

    def closeEvent(self, e):
        self.timer.stop()
        self.ui_timer.stop()
        self.armed = False
        for _ in range(3):   # make sure the Pi sees a disarmed frame on exit
            self.link.send(False, [0] * 6, self.tilt)
        self.pad.close()
        super().closeEvent(e)
        


class LevelBarSOC(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedHeight(8)
        self.value = 0

    def set(self, value):
        self.value = value
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        p.setPen(QPen(QColor(BORDER), 1))
        p.setBrush(QColor(WELL))
        p.drawRoundedRect(r, 4, 4)
        g = QLinearGradient(r.left(), 0, r.right(), 0)
        g.setColorAt(0, QColor("#2a6f5c"))
        g.setColorAt(1, QColor(ACCENT if self.value > 25 else DANGER))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(g)
        p.drawRoundedRect(QRectF(r.left() + 1, r.top() + 1, max(0.0, (r.width() - 2) * self.value / 100), r.height() - 2), 3, 3)


# ============================================================================
def main():
    ap = argparse.ArgumentParser(description="Camosun ROV topside console")
    ap.add_argument("--demo", action="store_true", help="simulate the vehicle (no network)")
    ap.add_argument("--host", default=PI_HOST)
    ap.add_argument("--cmd-port", type=int, default=CMD_PORT)
    ap.add_argument("--telem-port", type=int, default=TELEM_PORT)
    ap.add_argument("--diag", action="store_true", help="log control-loop timing every 5")
    args = ap.parse_args()

    app = QApplication(sys.argv)
    win = ConsoleWindow(args)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
