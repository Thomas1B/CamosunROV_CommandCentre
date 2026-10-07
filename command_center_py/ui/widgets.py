"""Custom-painted gauges and composite widgets used by the console window."""

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from command_center_py.config import DEADZONE, TILT_MIN, TILT_MAX
from command_center_py.ui.theme import (PANEL, HEAD, WELL, BORDER, BORDER2, GRID, TEXT, BRIGHT,
                          MUTED, DIM, LABEL, ACCENT, WARN, DANGER, OFF, mono, lab)


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
