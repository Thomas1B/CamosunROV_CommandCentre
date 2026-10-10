"""Main menu: the first screen of the command centre (from the ROV Main Menu design).

    CONNECT VEHICLE ... dialog: vehicle name / saved profile, Pi IP, ports. CONNECT
                        listens for telemetry for CONNECT_TIMEOUT_S; the console only
                        opens once the Pi answers, otherwise the dialog stays open.
    DEMO MODE ......... opens the console with a simulated vehicle (nothing transmitted)
    CONTROLLER MAP .... DualShock 3 and Xbox button maps side by side
    QUIT .............. closes the program

Navigation: arrow keys + Enter / Esc, or the controller D-pad + cross (A) / circle (B).
The dialogs are drawn as cards over a dimmed menu, like the design, rather than as
separate windows.
"""

import re
import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPen, QPixmap, QRadialGradient,
                           QTransform)
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from command_center_py import profiles
from command_center_py.config import (APP_BUILD, APP_VERSION, ARM_HOLD_S, CMD_PORT,
                                      CONNECT_TIMEOUT_S, DEFAULT_VEHICLE_NAME, PI_HOST, RATE_HZ,
                                      TELEM_PORT)
from command_center_py.link import Link, check_ipv4, check_port
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, GRID, HEAD,
                                        LABEL, MUTED, OFF, PANEL, SANS, WELL, lab, mono)
from command_center_py.ui.widgets import CONTROLLER_MAPS, LAYOUT, controller_map_body, key_chip

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:          # QtSvg missing - the menu just shows no logo
    QSvgRenderer = None

LOGO_SVG = Path(__file__).resolve().parent / "assets" / "camosunrov-logo-dark.svg"

SOFT = "#c9d3de"           # light grey used for secondary text in the design
FOOT = "#0a0e13"           # card footer background
OK_GREEN, OK_BORDER, OK_TEXT = "#123a30", "#2a6f5c", "#5ee7c1"
RED_BORDER, RED_DOT = "#7f2b2e", "#ff5c5c"


def spaced(font, px):
    """Return font with extra letter spacing (CSS letter-spacing in px)."""
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, px)
    return font


def slab(text, px, color, weight=QFont.Weight.Normal, spacing=0.0):
    w = lab(text, px, color, weight)
    if spacing:
        w.setFont(spaced(w.font(), spacing))
    return w


def button(text, px, width=None, css="", hover=""):
    b = QPushButton(text)
    b.setFont(mono(px, QFont.Weight.DemiBold))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    if width:
        b.setFixedWidth(width)
    b.setStyleSheet(f"QPushButton {{ {css} }} QPushButton:hover {{ {hover} }}")
    return b


def close_x(size):
    x = QPushButton("✕")
    x.setFixedSize(size, size)
    x.setFont(mono(round(size * 0.54)))
    x.setCursor(Qt.CursorShape.PointingHandCursor)
    x.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    x.setStyleSheet(f"QPushButton {{ border: none; border-radius: 2px; color: {LABEL}; background: transparent; }}"
                    f"QPushButton:hover {{ background: {BORDER}; color: {BRIGHT}; }}")
    return x


# ============================================================================
# MENU BACKGROUND + ROWS
# ============================================================================
class HeroBackground(QWidget):
    """Deep-water radial gradient with the faint sonar rings from the design."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # radial-gradient(110% 90% at 30% 40%, #12293a 0%, #0b1a25 45%, #070d13 100%)
        g = QRadialGradient(0, 0, 1)
        g.setColorAt(0.0, QColor("#12293a"))
        g.setColorAt(0.45, QColor("#0b1a25"))
        g.setColorAt(1.0, QColor("#070d13"))
        brush = QBrush(g)
        brush.setTransform(QTransform().translate(w * 0.30, h * 0.40).scale(w * 1.10, h * 0.90))
        p.fillRect(self.rect(), brush)

        cx, cy = w - 140, h / 2
        ring = lambda a: QPen(QColor(53, 208, 165, round(255 * a)), 1)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(ring(0.12))
        p.drawEllipse(QRectF(cx - 260, cy - 260, 520, 520))
        p.setPen(ring(0.18))
        p.drawEllipse(QRectF(cx - 120, cy - 120, 240, 240))
        p.fillRect(QRectF(cx, 0, 1, h), QColor(53, 208, 165, round(255 * 0.10)))
        p.fillRect(QRectF(0, round(cy), w, 1), QColor(53, 208, 165, round(255 * 0.06)))


class MenuRow(QFrame):
    """One menu entry. Hover selects it, click launches it."""

    def __init__(self, label, danger, on_hover, on_click):
        super().__init__()
        self.danger = danger
        self._on_hover, self._on_click = on_hover, on_click
        self.setObjectName("mrow")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 11, 14, 11)
        h.setSpacing(0)
        self.idx = lab("—", 10, OFF)
        self.idx.setFixedWidth(36)
        h.addWidget(self.idx)
        self.text = slab(label, 17, LABEL, QFont.Weight.Bold, 1.0)
        h.addWidget(self.text, 1)
        self._on = None
        self.set_selected(False)

    def set_selected(self, on):
        if on == self._on:
            return
        self._on = on
        if on:
            border, bg = (RED_BORDER, "rgba(42,16,18,0.85)") if self.danger else (OK_BORDER, "rgba(18,58,48,0.75)")
            idx_col = DANGER if self.danger else ACCENT
            txt_col = DANGER if self.danger else BRIGHT
        else:
            border, bg, idx_col, txt_col = "transparent", "transparent", OFF, LABEL
        self.setStyleSheet(f"QFrame#mrow {{ border: 1px solid {border}; border-radius: 3px; background: {bg}; }}")
        self.idx.setStyleSheet(f"color: {idx_col}; background: transparent;")
        self.text.setStyleSheet(f"color: {txt_col}; background: transparent;")

    def enterEvent(self, e):
        self._on_hover()
        super().enterEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._on_click()


# ============================================================================
# OVERLAY + CARDS
# ============================================================================
class Overlay(QWidget):
    """Dims the whole menu and centres one card on it. Clicking the dim area closes it."""

    def __init__(self, parent, card, on_backdrop):
        super().__init__(parent)
        self.card = card
        self._on_backdrop = on_backdrop
        lay = QGridLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.addWidget(card, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.hide()

    def paintEvent(self, e):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 128))

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self._on_backdrop()


class Card(QFrame):
    """Dialog card: title bar with ✕, a body and a footer strip."""

    def __init__(self, title, width, scale=1.0):
        super().__init__()
        s = lambda v: round(v * scale)
        self.setObjectName("card")
        self.setFixedWidth(s(width))
        self.setStyleSheet(f"QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER2}; border-radius: 4px; }}")
        root = QVBoxLayout(self)
        root.setContentsMargins(1, 1, 1, 1)
        root.setSpacing(0)

        head = QFrame()
        head.setObjectName("cardHead")
        head.setStyleSheet(f"QFrame#cardHead {{ background: {HEAD}; border-bottom: 1px solid {BORDER};"
                           f" border-top-left-radius: 3px; border-top-right-radius: 3px; }}")
        hh = QHBoxLayout(head)
        hh.setContentsMargins(s(16), s(12), s(12), s(12))
        hh.addWidget(slab(title, s(14), BRIGHT, QFont.Weight.Bold, s(14) * 0.06), 1)
        self.close_btn = close_x(s(24))
        hh.addWidget(self.close_btn)
        root.addWidget(head)

        self.body = QWidget()
        root.addWidget(self.body)

        self.foot = QFrame()
        self.foot.setObjectName("cardFoot")
        self.foot.setStyleSheet(f"QFrame#cardFoot {{ background: {FOOT}; border-top: 1px solid {BORDER};"
                                f" border-bottom-left-radius: 3px; border-bottom-right-radius: 3px; }}")
        self.foot_lay = QHBoxLayout(self.foot)
        self.foot_lay.setContentsMargins(s(16), s(10), s(16), s(10))
        self.foot_lay.setSpacing(s(8))
        root.addWidget(self.foot)


class ControllerMapCard(Card):
    """CONTROLLER MAPS: DualShock 3 and Xbox side by side. Esc / Enter / ✕ / OK / ○ / ✕ close it."""

    def __init__(self, on_close):
        super().__init__("CONTROLLER MAPS", 860)
        self.close_btn.clicked.connect(on_close)
        grid = QGridLayout(self.body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(1)
        self.body.setObjectName("mapGrid")
        self.body.setStyleSheet(f"QWidget#mapGrid {{ background: {BORDER}; }}")
        for col, kind in enumerate(("ds3", "xbox")):
            cell = QFrame()
            cell.setObjectName("mapCell")
            cell.setStyleSheet(f"QFrame#mapCell {{ background: {PANEL}; }}")
            v = QVBoxLayout(cell)
            v.setContentsMargins(16, 14, 16, 18)
            v.setSpacing(0)
            v.addWidget(slab(CONTROLLER_MAPS[kind]["short"], 12, ACCENT, QFont.Weight.Bold, 1.0))
            v.addWidget(controller_map_body(kind, ARM_HOLD_S))
            v.addStretch(1)
            grid.addWidget(cell, 0, col)

        self.foot_lay.addWidget(lab("Keyboard", 10, LABEL))
        self.foot_lay.addWidget(key_chip("SPACE", DANGER, RED_BORDER, 10))
        self.foot_lay.addWidget(lab("— E-STOP ·", 10, LABEL))
        self.foot_lay.addWidget(lab("ESC", 10, SOFT))
        self.foot_lay.addWidget(lab("to close", 10, LABEL))
        self.foot_lay.addStretch(1)
        ok = button("OK", 11, 72,
                    f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                    f"border-color: {ACCENT}; color: {ACCENT};")
        ok.clicked.connect(on_close)
        self.foot_lay.addWidget(ok)


class ConnectCard(Card):
    """CONNECT VEHICLE dialog.

    CONNECT opens the UDP link and streams disarmed, zero-thrust frames while it
    listens for telemetry. If the Pi answers within CONNECT_TIMEOUT_S, the live
    Link is handed to on_connected(link, vehicle_name) and the console opens.
    Otherwise the link is closed and the dialog stays open showing RETRY.
    """

    SCALE = 1.25      # the design draws this dialog at zoom 1.25

    MSG = {
        "idle":       ("Vehicle must be powered and the tether connected.", LABEL, None),
        "badip":      ("Enter a valid IPv4 address, e.g. 192.168.2.2", DANGER, RED_DOT),
        "badport":    ("Ports must be 1–65535", DANGER, RED_DOT),
        "sameport":   ("Command and telemetry ports must differ", DANGER, RED_DOT),
        "noname":     ("Enter a vehicle name to save a profile", DANGER, RED_DOT),
        "saved":      ('Profile "{name}" saved', ACCENT, ACCENT),
        "loaded":     ('Profile "{name}" loaded', ACCENT, ACCENT),
        "deleted":    ("Profile deleted", LABEL, MUTED),
        "connecting": ("Connecting to {ip} · cmd {cmd} · {left:.0f} s…", "#ffd479", "#ffd479"),
        "timeout":    ("No answer from {ip} — check tether and power", DANGER, RED_DOT),
        "error":      ("{error}", DANGER, RED_DOT),
    }

    def __init__(self, on_close, on_connected):
        super().__init__("CONNECT VEHICLE", 460, self.SCALE)
        self._on_close, self._on_connected = on_close, on_connected
        self.close_btn.clicked.connect(self.cancel)
        s = lambda v: round(v * self.SCALE)
        self._s = s
        self.state = "idle"
        self.error = ""
        self.link = None
        self.deadline = 0.0
        self.attempt = QTimer(self)
        self.attempt.setTimerType(Qt.TimerType.PreciseTimer)
        self.attempt.timeout.connect(self._attempt_tick)

        v = QVBoxLayout(self.body)
        v.setContentsMargins(s(16), s(16), s(16), s(16))
        v.setSpacing(s(14))

        def field_label(text):
            return slab(text, s(9), LABEL, spacing=s(9) * 0.1)

        def line_edit(text, placeholder):
            e = QLineEdit(text)
            e.setPlaceholderText(placeholder)
            e.setFont(mono(s(13)))
            e.setMinimumWidth(0)
            return e

        # vehicle name + saved-profile picker
        col = QVBoxLayout()
        col.setSpacing(s(6))
        col.addWidget(field_label("VEHICLE NAME"))
        row = QHBoxLayout()
        row.setSpacing(s(10))
        self.name_edit = line_edit(DEFAULT_VEHICLE_NAME, "ROV-01")
        self.name_edit.textEdited.connect(self._refresh)
        row.addWidget(self.name_edit, 1)
        self.profile_box = QComboBox()
        self.profile_box.setFixedWidth(s(150))
        self.profile_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)  # full row height
        self.profile_box.setFont(mono(s(11)))
        self.profile_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_box.setStyleSheet(
            f"QComboBox {{ padding: 0 {s(8)}px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT}; }}"
            f"QComboBox:focus {{ border-color: {ACCENT}; }}"
            f"QComboBox::drop-down {{ border: none; width: {s(16)}px; }}"
            f"QComboBox QAbstractItemView {{ background: {HEAD}; color: {SOFT}; border: 1px solid {BORDER2};"
            f" selection-background-color: {BORDER}; selection-color: {BRIGHT}; outline: none; }}")
        self.profile_box.activated.connect(self._pick_profile)
        row.addWidget(self.profile_box)
        col.addLayout(row)
        v.addLayout(col)

        col = QVBoxLayout()
        col.setSpacing(s(6))
        col.addWidget(field_label("IP ADDRESS"))
        self.ip_edit = line_edit(PI_HOST, "192.168.2.2")
        self.ip_edit.textEdited.connect(self._fields_edited)
        col.addWidget(self.ip_edit)
        v.addLayout(col)

        ports = QGridLayout()
        ports.setHorizontalSpacing(s(10))
        ports.setVerticalSpacing(s(6))
        ports.addWidget(field_label("COMMAND PORT · PI LISTENS"), 0, 0)
        ports.addWidget(field_label("TELEMETRY PORT · CONSOLE LISTENS"), 0, 1)
        self.cmd_edit = line_edit(str(CMD_PORT), str(CMD_PORT))
        self.tel_edit = line_edit(str(TELEM_PORT), str(TELEM_PORT))
        for i, e in enumerate((self.cmd_edit, self.tel_edit)):
            e.setMaxLength(5)
            e.textEdited.connect(self._fields_edited)
            ports.addWidget(e, 1, i)
        ports.setColumnStretch(0, 1)
        ports.setColumnStretch(1, 1)
        v.addLayout(ports)

        msg = QHBoxLayout()
        msg.setContentsMargins(0, s(10), 0, 0)
        msg.setSpacing(s(8))
        self.msg_dot = QLabel()
        self.msg_dot.setFixedSize(s(7), s(7))
        msg.addWidget(self.msg_dot)
        self.msg_lbl = lab("", s(11), LABEL)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setMinimumHeight(s(18))
        msg.addWidget(self.msg_lbl, 1)
        v.addLayout(msg)
        rate = lab(f"{RATE_HZ} Hz command rate ({1000 // RATE_HZ} ms) — fixed", s(11), LABEL)
        v.addWidget(rate)
        v.addSpacing(-s(6))

        # footer: SAVE PROFILE · DELETE ............ CANCEL  CONNECT
        self.save_btn = button("SAVE PROFILE", s(11), None,
                               f"padding: {s(7)}px {s(12)}px; border: 1px solid {GRID}; border-radius: 3px;"
                               f" background: {HEAD}; color: {SOFT};",
                               f"border-color: {ACCENT}; color: {ACCENT};")
        self.save_btn.clicked.connect(self.save_profile)
        self.foot_lay.addWidget(self.save_btn)
        self.del_btn = button("DELETE", s(11), None,
                              f"padding: {s(7)}px {s(10)}px; border: none; background: transparent; color: {LABEL};",
                              f"color: {DANGER};")
        self.del_btn.clicked.connect(self.delete_profile)
        self.foot_lay.addWidget(self.del_btn)
        self.foot_lay.addStretch(1)
        cancel = button("CANCEL", s(11), s(84),
                        f"padding: {s(7)}px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {SOFT};",
                        f"color: {BRIGHT};")
        cancel.clicked.connect(self.cancel)
        self.foot_lay.addWidget(cancel)
        self.conn_btn = button("CONNECT", s(11), s(120),
                               f"padding: {s(7)}px 0; border: 1px solid {OK_BORDER}; border-radius: 3px;"
                               f" background: {OK_GREEN}; color: {ACCENT};",
                               f"border-color: {ACCENT}; color: {OK_TEXT};")
        self.conn_btn.setFont(spaced(self.conn_btn.font(), s(11) * 0.06))
        self.conn_btn.clicked.connect(self.connect_vehicle)
        self.conn_fx = QGraphicsOpacityEffect(self.conn_btn)
        self.conn_btn.setGraphicsEffect(self.conn_fx)
        self.foot_lay.addWidget(self.conn_btn)

        self.profiles = []
        self.reload_profiles()
        self._refresh()

    # ---------------- state ----------------
    def opened(self):
        """Called each time the dialog is shown."""
        self.state = "idle"
        self.reload_profiles()
        self._refresh()
        self.ip_edit.setFocus()
        self.ip_edit.selectAll()

    def _set(self, state, error=""):
        self.state, self.error = state, error
        self._refresh()

    def _fields_edited(self, *_):
        for e in (self.cmd_edit, self.tel_edit):        # digits only, like the design
            t = re.sub(r"\D", "", e.text())
            if t != e.text():
                e.setText(t)
        self._set("idle")

    def _values(self):
        return (self.name_edit.text().strip(), self.ip_edit.text().strip(),
                self.cmd_edit.text().strip(), self.tel_edit.text().strip())

    def _validate(self):
        """Return (ip, cmd_port, telem_port) or None after showing what's wrong."""
        _, ip_text, cmd_text, tel_text = self._values()
        ip, _err = check_ipv4(ip_text)
        if ip is None:
            self._set("badip")
            return None
        cmd, tel = check_port(cmd_text), check_port(tel_text)
        if cmd is None or tel is None:
            self._set("badport")
            return None
        if cmd == tel:
            self._set("sameport")
            return None
        return ip, cmd, tel

    def _refresh(self, *_):
        s = self._s
        name, ip, cmd, _ = self._values()
        busy = self.state == "connecting"
        text, color, dot = self.MSG[self.state]
        left = max(0.0, self.deadline - time.monotonic())
        self.msg_lbl.setText(text.format(name=name, ip=ip, cmd=cmd, left=left + 0.5, error=self.error))
        self.msg_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self.msg_dot.setVisible(dot is not None)
        if dot:
            self.msg_dot.setStyleSheet(f"background: {dot}; border-radius: {s(7) // 2}px;")

        bad_ip = self.state == "badip"
        bad_port = self.state in ("badport", "sameport")
        for e, bad in ((self.name_edit, self.state == "noname"), (self.ip_edit, bad_ip),
                       (self.cmd_edit, bad_port), (self.tel_edit, bad_port)):
            e.setStyleSheet(
                f"QLineEdit {{ padding: {s(9)}px {s(10)}px; border: 1px solid {RED_BORDER if bad else GRID};"
                f" border-radius: 3px; background: {WELL}; color: {BRIGHT}; selection-background-color: {OK_BORDER}; }}"
                f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
                f"QLineEdit:disabled {{ color: {LABEL}; }}")
            e.setEnabled(not busy)
        self.profile_box.setEnabled(not busy and bool(self.profiles))
        self.save_btn.setEnabled(not busy)

        self.conn_btn.setText("CONNECTING…" if busy else "RETRY" if self.state == "timeout" else "CONNECT")
        self.conn_fx.setOpacity(0.7 if busy else 1.0)

        names = [p["name"] for p in self.profiles]
        self.del_btn.setVisible(name in names and not busy)
        self.profile_box.blockSignals(True)
        self.profile_box.setPlaceholderText("Load profile…" if names else "No saved profiles")
        self.profile_box.setCurrentIndex(names.index(name) if name in names else -1)
        self.profile_box.blockSignals(False)

    # ---------------- profiles ----------------
    def reload_profiles(self):
        self.profiles = profiles.load_profiles()
        self.profile_box.blockSignals(True)
        self.profile_box.clear()
        for p in self.profiles:
            self.profile_box.addItem(p["name"])
        self.profile_box.setCurrentIndex(-1)
        self.profile_box.blockSignals(False)

    def _pick_profile(self, index):
        if 0 <= index < len(self.profiles):
            p = self.profiles[index]
            self.name_edit.setText(p["name"])
            self.ip_edit.setText(p["ip"])
            self.cmd_edit.setText(str(p["cmd_port"]))
            self.tel_edit.setText(str(p["telem_port"]))
            self._set("loaded")

    def save_profile(self):
        name = self.name_edit.text().strip()
        if not name:
            self._set("noname")
            return
        vals = self._validate()
        if vals is None:
            return
        try:
            profiles.save_profile(name, *vals)
        except OSError as exc:
            self._set("error", f"Could not save profile: {exc}")
            return
        self.reload_profiles()
        self._set("saved")

    def delete_profile(self):
        profiles.delete_profile(self.name_edit.text().strip())
        self.reload_profiles()
        self._set("deleted")

    # ---------------- connecting ----------------
    def connect_vehicle(self):
        if self.state == "connecting":
            return
        vals = self._validate()
        if vals is None:
            return
        ip, cmd, tel = vals
        link = Link(ip, cmd, tel)
        if link.error:                       # e.g. telemetry port already in use
            link.close()
            self._set("error", link.error)
            return
        self.link = link
        self.deadline = time.monotonic() + CONNECT_TIMEOUT_S
        self._set("connecting")
        self.attempt.start(int(1000 / RATE_HZ))

    def _attempt_tick(self):
        link, now = self.link, time.monotonic()
        if link is None:
            self.attempt.stop()
            return
        link.send(False, [0] * 6, 0)         # disarmed, zero thrust - just asks the Pi to answer
        link.poll()
        if link.up(now):
            self.attempt.stop()
            self.link = None
            name = self.name_edit.text().strip() or link.addr[0]
            self.state = "idle"
            self._refresh()
            self._on_connected(link, name)
        elif now >= self.deadline:
            self.attempt.stop()
            self.link = None
            error = link.error
            link.close()
            if error:
                self._set("error", f"No answer — {error}")
            else:
                self._set("timeout")
        else:
            self._refresh()                  # countdown in the message line

    def abort_attempt(self):
        self.attempt.stop()
        if self.link is not None:
            self.link.close()
            self.link = None
        if self.state == "connecting":
            self.state = "idle"

    def cancel(self):
        self.abort_attempt()
        self._on_close()

    def key(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.cancel()
            return True
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not self.profile_box.view().isVisible():
            self.connect_vehicle()
            return True
        return False


# ============================================================================
# MAIN MENU WINDOW
# ============================================================================
class MainMenu(QWidget):
    ITEMS = ("CONNECT VEHICLE", "DEMO MODE", "CONTROLLER MAP", "QUIT")

    def __init__(self, pad, on_connected, on_demo):
        super().__init__()
        self.pad = pad
        self._on_connected, self._on_demo = on_connected, on_demo
        self.setWindowTitle("CamosunROV — Command Centre")
        self.setMinimumSize(1100, 720)
        self.resize(1440, 900)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(f"MainMenu {{ background: #0b0f14; }}"
                           f"QToolTip {{ background: {HEAD}; color: #d7e0ea; border: 1px solid {BORDER2}; }}")
        f = QFont()
        f.setFamilies(SANS)
        f.setPixelSize(13)
        self.setFont(f)

        self.sel = 0
        self.prev = {}
        self.pad_on = None
        self.xbox = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        hero = HeroBackground()
        root.addWidget(hero, 1)
        root.addWidget(self._build_statusbar())

        v = QVBoxLayout(hero)
        v.setContentsMargins(72, 64, 72, 0)
        v.setSpacing(0)

        # logo + title
        top = QHBoxLayout()
        top.setSpacing(28)
        logo = self._logo(168)
        if logo is not None:
            top.addWidget(logo, 0, Qt.AlignmentFlag.AlignVCenter)
        tcol = QVBoxLayout()
        tcol.setSpacing(6)
        tcol.addStretch(1)
        title = QLabel(f'<span style="font-size:60px">CamosunROV</span> - Command Centre')
        title.setFont(spaced(mono(44, QFont.Weight.Bold), 0.9))
        title.setStyleSheet(f"color: {BRIGHT}; background: transparent;")
        tcol.addWidget(title)
        tcol.addWidget(lab(f"v{APP_VERSION} · build {APP_BUILD}", 14, MUTED))
        tcol.addStretch(1)
        top.addLayout(tcol)
        top.addStretch(1)
        v.addLayout(top)
        v.addSpacing(64)

        # menu rows
        items = QWidget()
        items.setMaximumWidth(520)
        items.setStyleSheet("background: transparent;")
        iv = QVBoxLayout(items)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(4)
        self.rows = []
        for i, label in enumerate(self.ITEMS):
            r = MenuRow(label, label == "QUIT", lambda i=i: self.select(i), lambda i=i: self.launch(i))
            self.rows.append(r)
            iv.addWidget(r)
        v.addWidget(items)
        v.addSpacing(56)

        # key hints
        hints = QHBoxLayout()
        hints.setSpacing(28)
        self._hint(hints, "↑↓", "NAVIGATE")
        self.ok_cap = self._hint(hints, "✕", "SELECT")
        self.back_cap = self._hint(hints, "○", "BACK")
        hints.addStretch(1)
        v.addLayout(hints)
        v.addStretch(1)

        # dialog overlays
        self.connect_card = ConnectCard(self.close_overlay, self._connected)
        self.map_card = ControllerMapCard(self.close_overlay)
        self.connect_ov = Overlay(self, self.connect_card, self.connect_card.cancel)
        self.map_ov = Overlay(self, self.map_card, self.close_overlay)
        self.overlay = None

        self.select(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.resume()

    # ---------------- construction helpers ----------------
    def _logo(self, width):
        if QSvgRenderer is None or not LOGO_SVG.is_file():
            return None
        r = QSvgRenderer(str(LOGO_SVG))
        if not r.isValid():
            return None
        size = r.defaultSize()
        height = round(width * size.height() / size.width())
        dpr = max(1.0, self.devicePixelRatioF())
        pm = QPixmap(round(width * dpr), round(height * dpr))
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p)
        p.end()
        pm.setDevicePixelRatio(dpr)
        w = QLabel()
        w.setPixmap(pm)
        w.setFixedSize(width, height)
        w.setStyleSheet("background: transparent;")
        w.setToolTip("CamosunROV")
        return w

    def _hint(self, layout, cap_text, word):
        h = QHBoxLayout()
        h.setSpacing(8)
        cap = lab(cap_text, 13, BRIGHT)
        cap.setStyleSheet(f"color: {BRIGHT}; background: {HEAD}; border: 1px solid {GRID};"
                          f" border-radius: 3px; padding: 4px 9px;")
        cap.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        h.addWidget(cap)
        h.addWidget(slab(word, 13, LABEL, spacing=0.5))
        layout.addLayout(h)
        return cap

    def _build_statusbar(self):
        bar = QFrame()
        bar.setFixedHeight(22)
        bar.setObjectName("menuStatus")
        bar.setStyleSheet(f"QFrame#menuStatus {{ background: #10151c; border-top: 1px solid {BORDER}; }}")
        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 0, 8, 0)
        h.setSpacing(10)
        self.status_lbl = lab("", 10, SOFT)
        h.addWidget(self.status_lbl)
        h.addStretch(1)
        h.addWidget(lab("MAIN MENU", 10, MUTED))
        h.addWidget(lab("|", 10, GRID))
        h.addWidget(lab(f"v{APP_VERSION}", 10, MUTED))
        return bar

    # ---------------- navigation ----------------
    def select(self, i):
        self.sel = i % len(self.rows)
        for j, r in enumerate(self.rows):
            r.set_selected(j == self.sel)

    def launch(self, i=None):
        if i is not None:
            self.select(i)
        item = self.ITEMS[self.sel]
        if item == "CONNECT VEHICLE":
            self.open_overlay(self.connect_ov)
            self.connect_card.opened()
        elif item == "DEMO MODE":
            self._on_demo()
        elif item == "CONTROLLER MAP":
            self.open_overlay(self.map_ov)
        elif item == "QUIT":
            self.close()

    def open_overlay(self, ov):
        if self.overlay is not None:
            self.overlay.hide()
        self.overlay = ov
        ov.setGeometry(self.rect())
        ov.show()
        ov.raise_()
        if ov is self.map_ov:
            self.setFocus()

    def close_overlay(self):
        if self.overlay is not None:
            self.overlay.hide()
        self.overlay = None
        self.setFocus()

    def _connected(self, link, name):
        self.close_overlay()
        self._on_connected(link, name)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for ov in (self.connect_ov, self.map_ov):
            ov.setGeometry(self.rect())

    def keyPressEvent(self, e):
        k = e.key()
        if self.overlay is self.connect_ov:
            if not self.connect_card.key(e):
                super().keyPressEvent(e)
            return
        if self.overlay is self.map_ov:
            if k in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.close_overlay()
            return
        if k == Qt.Key.Key_Down:
            self.select(self.sel + 1)
        elif k == Qt.Key.Key_Up:
            self.select(self.sel - 1)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.launch()
        else:
            super().keyPressEvent(e)

    # ---------------- controller ----------------
    def pause(self):
        """Stop reading the controller (the console owns it while it is open)."""
        self.timer.stop()

    def resume(self):
        """Start reading the controller. Buttons already held don't count as presses."""
        self.prev = dict(self.pad.snapshot().buttons)
        self.timer.start(50)
        self.tick()

    def tick(self):
        pad = self.pad.snapshot()
        xbox = LAYOUT["kind"] == "xbox"     # set by the console's DUALSHOCK 3 / XBOX toggle
        if (pad.connected, xbox) != (self.pad_on, self.xbox):
            self.pad_on, self.xbox = pad.connected, xbox
            ok, back = ("A", "B") if xbox else ("✕", "○")
            self.ok_cap.setText(ok)
            self.back_cap.setText(back)
            self.status_lbl.setText(f"D-pad to navigate · {ok} to select" if pad.connected
                                    else "Arrow keys + Enter to navigate — or connect a controller")
        if not pad.connected:
            self.prev = {}
            return
        pressed = lambda b: pad.down(b) and not self.prev.get(b)
        if self.overlay is self.connect_ov:
            if pressed("circle"):
                self.connect_card.cancel()
            elif pressed("cross"):
                self.connect_card.connect_vehicle()
        elif self.overlay is self.map_ov:
            if pressed("cross") or pressed("circle"):
                self.close_overlay()
        else:
            if pressed("up"):
                self.select(self.sel - 1)
            if pressed("down"):
                self.select(self.sel + 1)
            if pressed("cross"):
                self.prev = dict(pad.buttons)
                self.launch()
                return
        self.prev = dict(pad.buttons)

    def closeEvent(self, e):
        self.connect_card.abort_attempt()
        self.timer.stop()
        super().closeEvent(e)
