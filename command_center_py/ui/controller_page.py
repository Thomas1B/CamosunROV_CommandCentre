"""Live views for the main menu's CONTROLLER PROFILES page (see ControllerProfilesCard in
start_window.py and the calibration logic in controller_profiles.py)."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from command_center_py.ui.theme import ACCENT, BORDER2, BRIGHT, GRID, LABEL, MUTED, WARN, WELL, mono


class StickCalView(QWidget):
    """One stick, raw input (-1..1 each way, up = +y):
        dark box ........ the full -1..+1 square
        teal dashed box . this profile's range (min..max per axis)
        amber box ....... the deadzone around the profile's centre (what reads as 0)
        cross ........... the profile's centre
        white dot ....... where the stick is right now (raw)
        teal trail ...... edge points seen during the ROTATE step
        amber arrow ..... FLICK step: the direction to flick next
        amber dots ...... FLICK step: where the stick settled after each flick"""

    def __init__(self, title):
        super().__init__()
        self.title = title
        self.setMinimumSize(170, 190)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.x = self.y = 0.0
        self.ax = self.ay = None           # profile axis dicts (center, deadzone, min, max)
        self.trail = []
        self.connected = False
        self.target = None
        self.points = []

    def set(self, x, y, ax, ay, connected, trail=None, target=None, points=None):
        self.x, self.y, self.ax, self.ay, self.connected = x, y, ax, ay, connected
        self.trail = trail if trail is not None else []
        self.target = target
        self.points = points if points is not None else []
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(mono(11, QFont.Weight.DemiBold))
        p.setPen(QColor(LABEL))
        p.drawText(QRectF(0, 0, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.title)
        side = min(self.width(), self.height() - 24) - 4
        box = QRectF((self.width() - side) / 2, 22, side, side)
        mx = lambda v: box.center().x() + v * side / 2
        my = lambda v: box.center().y() - v * side / 2
        p.fillRect(box, QColor(WELL))
        p.setPen(QPen(QColor(BORDER2), 1))
        p.drawRect(box)
        p.setPen(QPen(QColor(GRID), 1, Qt.PenStyle.DotLine))
        p.drawLine(QPointF(box.left(), my(0)), QPointF(box.right(), my(0)))
        p.drawLine(QPointF(mx(0), box.top()), QPointF(mx(0), box.bottom()))
        if self.ax and self.ay:
            ax, ay = self.ax, self.ay
            p.setPen(QPen(QColor(ACCENT), 1, Qt.PenStyle.DashLine))
            p.drawRect(QRectF(QPointF(mx(ax["min"]), my(ay["max"])), QPointF(mx(ax["max"]), my(ay["min"]))))
            # deadzone in raw units on each side of the centre
            dz = lambda a, side_: a["deadzone"] * ((a["max"] - a["center"]) if side_ > 0 else (a["center"] - a["min"]))
            dzr = QRectF(QPointF(mx(ax["center"] - dz(ax, -1)), my(ay["center"] + dz(ay, 1))),
                         QPointF(mx(ax["center"] + dz(ax, 1)), my(ay["center"] - dz(ay, -1))))
            c = QColor(WARN)
            c.setAlpha(50)
            p.fillRect(dzr, c)
            p.setPen(QPen(QColor(WARN), 1))
            p.drawRect(dzr)
            cx, cy = mx(ax["center"]), my(ay["center"])
            p.drawLine(QPointF(cx - 6, cy), QPointF(cx + 6, cy))
            p.drawLine(QPointF(cx, cy - 6), QPointF(cx, cy + 6))
        if self.trail:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(ACCENT))
            for tx, ty in self.trail[-400:]:
                p.drawEllipse(QPointF(mx(tx), my(ty)), 1.5, 1.5)
        if self.target is not None:              # flick: arrow from the middle towards the target
            rad = math.radians(self.target)
            tip = QPointF(mx(0.85 * math.cos(rad)), my(0.85 * math.sin(rad)))
            p.setPen(QPen(QColor(WARN), 2))
            p.drawLine(QPointF(mx(0.25 * math.cos(rad)), my(0.25 * math.sin(rad))), tip)
            for da in (150, -150):
                h = math.radians(self.target + da)
                p.drawLine(tip, QPointF(tip.x() + 9 * math.cos(h), tip.y() - 9 * math.sin(h)))
        if self.points:
            p.setPen(QPen(QColor("#000000"), 0.5))
            p.setBrush(QColor(WARN))
            for px_, py_ in self.points:
                p.drawEllipse(QPointF(mx(px_), my(py_)), 2.5, 2.5)
        if self.connected:
            p.setPen(QPen(QColor("#000000"), 1))
            p.setBrush(QColor(BRIGHT))
            p.drawEllipse(QPointF(mx(self.x), my(self.y)), 5, 5)


class TriggerCalBar(QWidget):
    """One trigger, raw 0..1 left to right: fill = now, amber = rest + deadzone, teal tick = max."""

    def __init__(self, title):
        super().__init__()
        self.title = title
        self.setFixedHeight(34)
        self.setMinimumWidth(150)
        self.v = 0.0
        self.t = None
        self.peak = None

    def set(self, v, t, peak=None):
        self.v, self.t, self.peak = v, t, peak
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(mono(11, QFont.Weight.DemiBold))
        p.setPen(QColor(LABEL))
        p.drawText(QRectF(0, 0, 70, 34), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.title)
        bar = QRectF(72, 9, self.width() - 76, 16)
        x = lambda v: bar.left() + max(0.0, min(1.0, v)) * bar.width()
        p.fillRect(bar, QColor(WELL))
        f = QRectF(bar)
        f.setRight(x(self.v))
        p.fillRect(f, QColor("#2c6f60"))
        if self.t:
            c = QColor(WARN)
            c.setAlpha(60)
            rest, top = self.t["rest"], self.t["rest"] + self.t["deadzone"] * (self.t["max"] - self.t["rest"])
            p.fillRect(QRectF(QPointF(x(rest), bar.top()), QPointF(x(top), bar.bottom())), c)
            p.setPen(QPen(QColor(ACCENT), 2))
            p.drawLine(QPointF(x(self.t["max"]), bar.top() - 3), QPointF(x(self.t["max"]), bar.bottom() + 3))
        if self.peak is not None:
            p.setPen(QPen(QColor(BRIGHT), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(x(self.peak), bar.top() - 3), QPointF(x(self.peak), bar.bottom() + 3))
        p.setPen(QPen(QColor(BORDER2), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(bar)
        p.setPen(QColor(MUTED))
