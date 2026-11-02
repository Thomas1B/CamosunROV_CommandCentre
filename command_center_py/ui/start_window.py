"""Main menu: the first screen of the command centre (from the ROV Main Menu design).

    CONNECT VEHICLE ... dialog: vehicle name / saved profile, Pi IP, ports. CONNECT
                        listens for telemetry for CONNECT_TIMEOUT_S; the console only
                        opens once the Pi answers, otherwise the dialog stays open.
    DEMO MODE ......... opens the console with a simulated vehicle (nothing transmitted)
    VIEW LOGS ......... saved console session logs (logs/): preview, export, delete
    CONTROLLER MAP .... DualShock 3 and Xbox button maps side by side
    CONTROLLER PROFILES calibrate a controller (drift, deadzone, range) and save it
    QUIT .............. closes the program

Navigation: arrow keys + Enter / Esc, or the controller D-pad + cross (A) / circle (B).
The dialogs are drawn as cards over a dimmed menu, like the design, rather than as
separate windows.
"""

import re
import time
from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QFont, QPainter, QPen, QPixmap,
                           QRadialGradient, QTransform)
from PySide6.QtWidgets import (QComboBox, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
                               QDoubleSpinBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
                               QTabWidget, QVBoxLayout, QWidget)

from command_center_py import controller_profiles as cp
from command_center_py import profiles
from command_center_py.config import (APP_BUILD, APP_VERSION, ARM_HOLD_S, CMD_PORT,
                                      CONNECT_TIMEOUT_S, DEFAULT_VEHICLE_NAME, PI_HOST, RATE_HZ,
                                      LOGS_DIR, TELEM_PORT, VIDEO_PORT)
from command_center_py.event_log import EVENT_COLS, MARK_COLS, list_logs
from command_center_py.link import Link, check_ipv4, check_port
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, GRID, HEAD,
                                        DIM, LABEL, MUTED, OFF, PANEL, SANS, WARN, WELL, combo_arrow_css, lab, mono)
from command_center_py.ui.controller_page import StickCalView, TriggerCalBar
from command_center_py.ui.log_dialog import export_session, log_table
from command_center_py.ui.reference_fields import RefFields
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
        # Widen to fit the longest line in the installed font (no wrapping, nothing cut off).
        self.setFixedWidth(max(self.width(), self.sizeHint().width() + 8))


class ConnectCard(Card):
    """CONNECT VEHICLE dialog.

    CONNECT opens the UDP link and streams disarmed, zero-thrust frames while it
    listens for telemetry. If the Pi answers within CONNECT_TIMEOUT_S, the live
    Link is handed to on_connected(link, vehicle_name, controller_profile) and the console
    opens; controller_profile is the CONTROLLER PROFILE choice (NONE or a profile name).
    Otherwise the link is closed and the dialog stays open showing RETRY.
    """

    SCALE = 1.25      # the design draws this dialog at zoom 1.25

    MSG = {
        "idle":       ("", LABEL, None),
        "badip":      ("Enter a valid IPv4 address, e.g. 192.168.2.2", DANGER, RED_DOT),
        "badport":    ("Ports must be 1–65535", DANGER, RED_DOT),
        "sameport":   ("Command, telemetry and video ports must all differ", DANGER, RED_DOT),
        "badref":     ("Surface pressure must be 800–1100 hPa (80–110 kPa) and water density 900–1100 kg/m³",
                       DANGER, RED_DOT),
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
            return slab(text, s(9), BRIGHT, spacing=s(9) * 0.1)

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
        self.name_edit.textEdited.connect(self._name_edited)
        row.addWidget(self.name_edit, 1)
        self.profile_box = QComboBox()
        self.profile_box.setFixedWidth(s(150))
        self.profile_box.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)  # full row height
        self.profile_box.setFont(mono(s(11)))
        self.profile_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.profile_box.setStyleSheet(
            f"QComboBox {{ padding: 0 {s(8)}px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT}; }}"
            f"QComboBox:focus {{ border-color: {ACCENT}; }}"
            + combo_arrow_css(s(24)) +
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
        self.vid_edit = line_edit(str(VIDEO_PORT), str(VIDEO_PORT))
        for i, e in enumerate((self.cmd_edit, self.tel_edit)):
            e.setMaxLength(5)
            e.textEdited.connect(self._fields_edited)
            ports.addWidget(e, 1, i)
        # second row: VIDEO PORT under COMMAND PORT
        ports.addWidget(field_label("VIDEO PORT · CONSOLE LISTENS"), 2, 0)
        self.vid_edit.setMaxLength(5)
        self.vid_edit.textEdited.connect(self._fields_edited)
        ports.addWidget(self.vid_edit, 3, 0)
        ports.setRowMinimumHeight(2, s(9) + s(10))     # gap above the second row of ports
        ports.setColumnStretch(0, 1)
        ports.setColumnStretch(1, 1)
        v.addLayout(ports)

        # Bar30 reference values: surface pressure, water density, second-order cal
        self.ref_fields = RefFields(self.SCALE, label_color=BRIGHT, readable_units=True)
        self.ref_fields.edited.connect(lambda: self._set("idle"))
        v.addWidget(self.ref_fields)
        # under the reference values: which controller profile the console uses
        # (defaults, or a saved one). Starts on Defaults every time the dialog opens.
        col = QVBoxLayout()
        col.setSpacing(s(6))
        col.addWidget(field_label("CONTROLLER PROFILE"))
        self.ctl_box = QComboBox()
        self.ctl_box.setFont(mono(s(11)))
        self.ctl_box.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ctl_box.setFixedHeight(s(38))
        self.ctl_box.setToolTip("Make and edit profiles in CONTROLLER PROFILES on the main menu")
        self.ctl_box.setStyleSheet(
            f"QComboBox {{ padding: 0 {s(8)}px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT}; }}"
            f"QComboBox:focus {{ border-color: {ACCENT}; }}"
            + combo_arrow_css(s(24)) +
            f"QComboBox QAbstractItemView {{ background: {HEAD}; color: {SOFT}; border: 1px solid {BORDER2};"
            f" selection-background-color: {BORDER}; selection-color: {BRIGHT}; outline: none; }}")
        col.addWidget(self.ctl_box)
        hint = lab("Make and edit profiles in CONTROLLER PROFILES on the main menu", s(10), MUTED)
        hint.setWordWrap(True)
        col.addWidget(hint)
        v.addLayout(col)

        self.msg_row = QWidget()                 # hidden while there is no message (idle)
        msg = QHBoxLayout(self.msg_row)
        msg.setContentsMargins(0, s(10), 0, 0)
        msg.setSpacing(s(8))
        self.msg_dot = QLabel()
        self.msg_dot.setFixedSize(s(7), s(7))
        msg.addWidget(self.msg_dot)
        self.msg_lbl = lab("", s(11), LABEL)
        self.msg_lbl.setWordWrap(True)
        self.msg_lbl.setMinimumHeight(s(18))
        msg.addWidget(self.msg_lbl, 1)
        v.addWidget(self.msg_row)
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
        self.reload_controller_profiles()
        self._refresh()

    # ---------------- state ----------------
    def opened(self):
        """Called each time the dialog is shown."""
        self.state = "idle"
        self.reload_profiles()
        self.reload_controller_profiles()
        self._refresh()
        self.ip_edit.setFocus()
        self.ip_edit.selectAll()

    def _set(self, state, error=""):
        self.state, self.error = state, error
        self._refresh()

    def _fields_edited(self, *_):
        for e in (self.cmd_edit, self.tel_edit, self.vid_edit):   # digits only, like the design
            t = re.sub(r"\D", "", e.text())
            if t != e.text():
                e.setText(t)
        self._set("idle")

    # Profile messages ("saved", "loaded", ...) describe the name as it was at that
    # moment; once the user edits the name they no longer apply, so drop back to idle.
    # Other states (bad IP/port, timeout) are about other fields and stay visible.
    _NAME_STATES = ("saved", "loaded", "deleted", "noname")

    def _name_edited(self, *_):
        if self.state in self._NAME_STATES:
            self._set("idle")
        else:
            self._refresh()

    def _values(self):
        return (self.name_edit.text().strip(), self.ip_edit.text().strip(),
                self.cmd_edit.text().strip(), self.tel_edit.text().strip(),
                self.vid_edit.text().strip())

    def _validate(self):
        """Return (ip, cmd_port, telem_port, video_port, refs) or None after showing what's wrong."""
        _, ip_text, cmd_text, tel_text, vid_text = self._values()
        ip, _err = check_ipv4(ip_text)
        if ip is None:
            self._set("badip")
            return None
        cmd, tel, vid = check_port(cmd_text), check_port(tel_text), check_port(vid_text)
        if cmd is None or tel is None or vid is None:
            self._set("badport")
            return None
        if len({cmd, tel, vid}) < 3:
            self._set("sameport")
            return None
        refs, err = self.ref_fields.values()
        if err:
            self._set("badref")
            return None
        return ip, cmd, tel, vid, refs

    def _refresh(self, *_):
        s = self._s
        name, ip, cmd, _, _ = self._values()
        busy = self.state == "connecting"
        text, color, dot = self.MSG[self.state]
        left = max(0.0, self.deadline - time.monotonic())
        self.msg_lbl.setText(text.format(name=name, ip=ip, cmd=cmd, left=left + 0.5, error=self.error))
        self.msg_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        self.msg_row.setVisible(bool(text))
        self.msg_dot.setVisible(dot is not None)
        if dot:
            self.msg_dot.setStyleSheet(f"background: {dot}; border-radius: {s(7) // 2}px;")

        bad_ip = self.state == "badip"
        bad_port = self.state in ("badport", "sameport")
        for e, bad in ((self.name_edit, self.state == "noname"), (self.ip_edit, bad_ip),
                       (self.cmd_edit, bad_port), (self.tel_edit, bad_port), (self.vid_edit, bad_port)):
            e.setStyleSheet(
                f"QLineEdit {{ padding: {s(9)}px {s(10)}px; border: 1px solid {RED_BORDER if bad else GRID};"
                f" border-radius: 3px; background: {WELL}; color: {BRIGHT}; selection-background-color: {OK_BORDER}; }}"
                f"QLineEdit:focus {{ border-color: {ACCENT}; }}"
                f"QLineEdit:disabled {{ color: {LABEL}; }}")
            e.setEnabled(not busy)
        self.profile_box.setEnabled(not busy and bool(self.profiles))
        self.save_btn.setEnabled(not busy)
        self.ref_fields.setEnabled(not busy)

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

    def reload_controller_profiles(self):
        """Defaults, then every saved controller profile; Defaults selected."""
        self.ctl_box.clear()
        for choice in [cp.NONE] + [p.name for p in cp.load_all()]:
            self.ctl_box.addItem(cp.describe(choice), choice)
        self.ctl_box.setCurrentIndex(0)

    def controller_choice(self):
        return self.ctl_box.currentData() or cp.NONE

    def _pick_profile(self, index):
        if 0 <= index < len(self.profiles):
            p = self.profiles[index]
            self.name_edit.setText(p["name"])
            self.ip_edit.setText(p["ip"])
            self.cmd_edit.setText(str(p["cmd_port"]))
            self.tel_edit.setText(str(p["telem_port"]))
            self.vid_edit.setText(str(p["video_port"]))
            self.ref_fields.set_values(p["refs"])
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
        ip, cmd, tel, vid, refs = vals
        link = Link(ip, cmd, tel, vid, refs)
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
            self._on_connected(link, name, controller_profile=self.controller_choice())
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
        # Esc cancels. There is deliberately no Enter = CONNECT: connecting starts sending
        # command packets to the ROV, so it is mouse (CONNECT button) or controller (CROSS) only.
        if e.key() == Qt.Key.Key_Escape:
            self.cancel()
            return True
        return False


class ResizeGrip(QWidget):
    """Corner handle that resizes its card by dragging. The card stays centred on the menu,
    so it grows by twice the mouse movement (both edges move) to keep the corner under the
    pointer. Size is limited to the card's minimum and the menu window minus a 24 px margin."""

    SIZE = 14

    def __init__(self, card, min_w, min_h):
        super().__init__(card)
        self.card, self.min_w, self.min_h = card, min_w, min_h
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip("Drag to resize")
        self._start = None

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(MUTED), 1.2))
        s = self.SIZE - 3
        p.drawLine(s, 3, 3, s)
        p.drawLine(s, 7, 7, s)

    def clamp(self, w, h):
        ov = self.card.parentWidget()
        max_w = max(self.min_w, ov.width() - 48) if ov is not None else w
        max_h = max(self.min_h, ov.height() - 48) if ov is not None else h
        return max(self.min_w, min(max_w, w)), max(self.min_h, min(max_h, h))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._start = (e.globalPosition().toPoint(), self.card.width(), self.card.height())

    def mouseMoveEvent(self, e):
        if self._start is None:
            return
        pos, w, h = self._start
        d = e.globalPosition().toPoint() - pos
        self.card.setFixedSize(*self.clamp(w + 2 * d.x(), h + 2 * d.y()))

    def mouseReleaseEvent(self, e):
        self._start = None


class LogsCard(Card):
    """SESSION LOGS: every console session saved in logs/, newest first.

    Left: the list of sessions (start time, vehicle, events, marks, length). Right: the
    selected session in the same OPERATOR MARKS / ALL EVENTS tables as the exit pop-up.
    Footer: OPEN FOLDER, DELETE (click twice), EXPORT... (.xlsx / .csv / .pdf), CLOSE.
    Esc / circle (B) / ✕ / CLOSE close it; D-pad or arrow keys pick a session.
    Resizable: drag the grip in the bottom-right corner (kept while the program runs).
    """

    MIN_W, MIN_H = 720, 380

    def __init__(self, on_close):
        super().__init__("SESSION LOGS", 1040)
        self._on_close = on_close
        self.close_btn.clicked.connect(on_close)
        self.logs = []
        self._del_armed = False

        h = QHBoxLayout(self.body)
        h.setContentsMargins(14, 14, 14, 10)
        h.setSpacing(14)

        self.list = QListWidget()
        self.list.setFixedWidth(270)
        self.list.setFont(mono(12))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setStyleSheet(
            f"QListWidget {{ background: {WELL}; border: 1px solid {BORDER}; outline: none; }}"
            f"QListWidget::item {{ color: {LABEL}; padding: 8px 10px; border-bottom: 1px solid {BORDER}; }}"
            f"QListWidget::item:hover {{ color: {BRIGHT}; }}"
            f"QListWidget::item:selected {{ background: rgba(18,58,48,0.75); color: {BRIGHT};"
            f" border-left: 2px solid {ACCENT}; }}"
            f"QScrollBar {{ background: {PANEL}; border: none; width: 10px; }}"
            f"QScrollBar::handle {{ background: {GRID}; border-radius: 4px; min-height: 24px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}")
        self.list.currentRowChanged.connect(self._show)
        h.addWidget(self.list)

        right = QVBoxLayout()
        right.setSpacing(6)
        self.info = lab("", 12, SOFT)
        self.info.setWordWrap(True)
        right.addWidget(self.info)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.tabBar().setFont(mono(11, QFont.Weight.DemiBold))
        self.tabs.setStyleSheet(
            f"QTabWidget::pane {{ border: none; background: {PANEL}; }}"
            f"QTabBar::tab {{ background: {PANEL}; color: {LABEL}; padding: 6px 12px;"
            f" border: none; border-bottom: 2px solid transparent; }}"
            f"QTabBar::tab:selected {{ color: {BRIGHT}; border-bottom: 2px solid {ACCENT}; }}"
            f"QTabBar::tab:hover {{ color: {BRIGHT}; }}")
        right.addWidget(self.tabs, 1)
        self.empty = lab("No session logs yet. A log is saved in logs/ every time the console runs.", 12, LABEL)
        self.empty.setWordWrap(True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.empty, 1)
        h.addLayout(right, 1)
        self.layout().setStretchFactor(self.body, 1)      # extra height goes to the tables
        self.setFixedSize(1040, 600)
        self.grip = ResizeGrip(self, self.MIN_W, self.MIN_H)

        # footer: OPEN FOLDER  DELETE  status ........ EXPORT...  CLOSE
        folder = button("OPEN FOLDER", 11, None,
                        f"padding: 6px 12px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT};",
                        f"border-color: {ACCENT}; color: {ACCENT};")
        folder.clicked.connect(self._open_folder)
        self.foot_lay.addWidget(folder)
        self.del_btn = button("DELETE", 11, 190,
                              f"padding: 6px 0; border: 1px solid {RED_BORDER}; border-radius: 3px; background: #2a1416; color: {DANGER};",
                              f"border-color: {DANGER};")
        self.del_btn.clicked.connect(self._delete)
        self.foot_lay.addWidget(self.del_btn)
        self.status = lab("", 11, LABEL)
        self.status.setWordWrap(True)
        self.foot_lay.addWidget(self.status, 1)
        self.export_btn = button("EXPORT…", 11, 100,
                                 f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {SOFT};",
                                 f"color: {BRIGHT}; border-color: {LABEL};")
        self.export_btn.clicked.connect(self._export)
        self.foot_lay.addWidget(self.export_btn)
        close = button("CLOSE", 11, 84,
                       f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                       f"border-color: {ACCENT}; color: {ACCENT};")
        close.clicked.connect(on_close)
        self.foot_lay.addWidget(close)
        for b in (self.del_btn, self.export_btn):
            b.setStyleSheet(b.styleSheet() + f" QPushButton:disabled {{ color: {MUTED}; border-color: {BORDER2}; background: transparent; }}")

    # ---------------- state ----------------
    def opened(self):
        """Called each time the card is shown: re-reads logs/ (new sessions, deleted files)."""
        self.setFixedSize(*self.grip.clamp(self.width(), self.height()))   # menu may have shrunk
        self.logs = list_logs()
        self.list.blockSignals(True)
        self.list.clear()
        for lg in self.logs:
            n_ev, n_mk = len(lg.rows), len(lg.marks())
            item = QListWidgetItem(f"{lg.started}\n{lg.vehicle}  ·  {n_ev} event{'' if n_ev == 1 else 's'}"
                                   f"  ·  {n_mk} mark{'' if n_mk == 1 else 's'}")
            if lg.error:
                item.setToolTip(lg.error)
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._say(LABEL, "")
        self.list.setCurrentRow(0 if self.logs else -1)
        self._show(self.list.currentRow())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        g = self.grip
        g.move(self.width() - g.width() - 2, self.height() - g.height() - 2)
        g.raise_()

    def current(self):
        i = self.list.currentRow()
        return self.logs[i] if 0 <= i < len(self.logs) else None

    def _show(self, i):
        self._disarm_delete()
        lg = self.current()
        has = lg is not None
        self.tabs.setVisible(has)
        self.empty.setVisible(not has)
        self.del_btn.setEnabled(has)
        self.export_btn.setEnabled(has and not lg.error)
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()
        if not has:
            self.info.setText("")
            return
        if lg.error:
            self.info.setText(lg.error)
            return
        rows, marks = lg.rows, lg.marks()
        utc = f"  ·  UTC {rows[0]['utc_time'][:19]} → {rows[-1]['utc_time'][11:19]}" if rows else ""
        self.info.setText(f"logs/{lg.path.name}\n{lg.vehicle}  ·  length {lg.duration()}{utc}")
        self.tabs.addTab(log_table(marks, MARK_COLS), f"OPERATOR MARKS ({len(marks)})")
        self.tabs.addTab(log_table(rows, EVENT_COLS), f"ALL EVENTS ({len(rows)})")
        self.tabs.setCurrentIndex(0 if marks else 1)

    def step(self, d):
        if self.logs:
            self.list.setCurrentRow(max(0, min(len(self.logs) - 1, self.list.currentRow() + d)))

    def _say(self, color, text):
        self.status.setStyleSheet(f"color: {color}; background: transparent;")
        self.status.setText(text)

    # ---------------- footer ----------------
    def _open_folder(self):
        try:
            LOGS_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self._say(DANGER, f"Can't open logs/ — {e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(LOGS_DIR)))

    def _delete(self):
        lg = self.current()
        if lg is None:
            return
        if not self._del_armed:              # first click arms, second deletes
            self._del_armed = True
            self.del_btn.setText("CLICK AGAIN TO DELETE")
            self._say(WARN, f"Deletes {lg.path.name}. Can't be undone.")
            QTimer.singleShot(4000, self._disarm_delete)
            return
        err = lg.delete()
        if err:
            self._disarm_delete()
            self._say(DANGER, err)
            return
        row = self.list.currentRow()
        self.opened()
        self.list.setCurrentRow(min(row, len(self.logs) - 1))
        self._say(LABEL, f"Deleted {lg.path.name}")

    def _disarm_delete(self):
        if self._del_armed:
            self._del_armed = False
            self.del_btn.setText("DELETE")
            self._say(LABEL, "")

    def _export(self):
        lg = self.current()
        if lg is None or lg.error:
            return
        path, err = export_session(self.window(), lg)
        if err:
            self._say(DANGER, err)
        elif path:
            self._say(ACCENT, f"Exported {Path(path).name}")

    def key(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self._on_close()
        elif k == Qt.Key.Key_Down:
            self.step(1)
        elif k == Qt.Key.Key_Up:
            self.step(-1)
        else:
            return False
        return True


LIST_CSS = (f"QListWidget {{ background: {WELL}; border: 1px solid {BORDER}; outline: none; }}"
            f"QListWidget::item {{ color: {LABEL}; padding: 8px 10px; border-bottom: 1px solid {BORDER}; }}"
            f"QListWidget::item:hover {{ color: {BRIGHT}; }}"
            f"QListWidget::item:selected {{ background: rgba(18,58,48,0.75); color: {BRIGHT}; border-left: 2px solid {ACCENT}; }}"
            f"QScrollBar {{ background: {PANEL}; border: none; width: 10px; }}"
            f"QScrollBar::handle {{ background: {GRID}; border-radius: 4px; min-height: 24px; }}"
            f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}")
EDIT_CSS = (f"QLineEdit {{ padding: 7px 9px; border: 1px solid {GRID}; border-radius: 3px; background: {WELL}; color: {BRIGHT};"
            f" selection-background-color: {OK_BORDER}; }} QLineEdit:focus {{ border-color: {ACCENT}; }}")
SPIN_CSS = (f"QDoubleSpinBox {{ padding: 4px 7px; border: 1px solid {GRID}; border-radius: 3px; background: {WELL}; color: {BRIGHT};"
            f" selection-background-color: {OK_BORDER}; }} QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}"
            # arrows hidden here, not with setButtonSymbols(NoButtons): that plus a stylesheet hides the text
            f" QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{ width: 0; border: none; }}")


class ControllerProfilesCard(Card):
    """CONTROLLER PROFILES: calibrate a controller and save it as a profile.

    Left: saved profiles, NEW, DELETE.
    Right: name + controller it belongs to, live stick and trigger views, the CALIBRATE wizard
    (REST -> ROTATE -> TRIGGERS) and every value as an editable field. SAVE writes
    controller_profiles/<name>.json. Mouse / keyboard only: the controller is being
    calibrated, so its buttons don't operate this page. Esc or CLOSE closes it.
    """

    MIN_W, MIN_H = 900, 560
    STEP_TEXT = {
        "ready": "Hands off both sticks and both triggers, then press OK to start.",
        "left_flick": "1a / 3  LEFT STICK — {flick}   {n} / {N} flicks",
        "left_cw": "1b / 3  LEFT STICK — push it to the edge and rotate CLOCKWISE ↻   {n} / {N} turns",
        "left_ccw": "1c / 3  LEFT STICK — now rotate COUNTER-CLOCKWISE ↺   {n} / {N} turns",
        "right_flick": "2a / 3  RIGHT STICK — {flick}   {n} / {N} flicks",
        "right_cw": "2b / 3  RIGHT STICK — push it to the edge and rotate CLOCKWISE ↻   {n} / {N} turns",
        "right_ccw": "2c / 3  RIGHT STICK — now rotate COUNTER-CLOCKWISE ↺   {n} / {N} turns",
        "triggers": "3 / 3  TRIGGERS — press L2 and R2 (LT / RT) all the way down, release, then press FINISH.",
    }

    def __init__(self, on_close):
        super().__init__("CONTROLLER PROFILES", 1120)
        self._on_close = on_close
        self.close_btn.clicked.connect(self.close_card)
        self.profiles = []
        self.edit = cp.ControllerProfile()
        self.dirty = False
        self.cal = None
        self.trail = {"l": [], "r": []}
        self.pad_name = ""
        self._armed = None                    # "delete" / "close" while waiting for a 2nd click
        self._loading = False

        h = QHBoxLayout(self.body)
        h.setContentsMargins(14, 14, 14, 10)
        h.setSpacing(14)

        # ---- left: saved profiles ----
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addWidget(slab("SAVED PROFILES", 10, LABEL, QFont.Weight.Bold, 1.0))
        self.list = QListWidget()
        self.list.setFixedWidth(250)
        self.list.setFont(mono(12))
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setStyleSheet(LIST_CSS)
        self.list.currentRowChanged.connect(self._pick)
        left.addWidget(self.list, 1)
        lb = QHBoxLayout()
        lb.setSpacing(6)
        new = button("NEW", 11, None, f"padding: 6px 12px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT};",
                     f"border-color: {ACCENT}; color: {ACCENT};")
        new.clicked.connect(self.new_profile)
        lb.addWidget(new)
        self.del_btn = button("DELETE", 11, None, f"padding: 6px 12px; border: none; background: transparent; color: {LABEL};",
                              f"color: {DANGER};")
        self.del_btn.clicked.connect(self._delete)
        lb.addWidget(self.del_btn)
        lb.addStretch(1)
        left.addLayout(lb)
        h.addLayout(left)

        # ---- right: editor ----
        right = QVBoxLayout()
        right.setSpacing(10)
        top = QGridLayout()
        top.setHorizontalSpacing(10)
        top.setVerticalSpacing(4)
        top.addWidget(slab("PROFILE NAME", 9, BRIGHT, spacing=0.9), 0, 0)
        top.addWidget(slab("CONTROLLER · NOTE OF WHICH ONE IT'S FOR", 9, BRIGHT, spacing=0.9), 0, 1, 1, 2)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. Josh DS3")
        self.name_edit.textEdited.connect(self._edited)
        self.ctrl_edit = QLineEdit()
        self.ctrl_edit.setPlaceholderText("connected controller's name")
        self.ctrl_edit.textEdited.connect(self._edited)
        for e in (self.name_edit, self.ctrl_edit):
            e.setFont(mono(13))
            e.setStyleSheet(EDIT_CSS)
        top.addWidget(self.name_edit, 1, 0)
        top.addWidget(self.ctrl_edit, 1, 1)
        self.use_btn = button("USE CONNECTED", 11, None,
                              f"padding: 7px 10px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT};",
                              f"border-color: {ACCENT}; color: {ACCENT};")
        self.use_btn.clicked.connect(self._use_connected)
        top.addWidget(self.use_btn, 1, 2)
        top.setColumnStretch(0, 2)
        top.setColumnStretch(1, 3)
        self.pad_lbl = lab("", 11, LABEL)
        top.addWidget(self.pad_lbl, 2, 0, 1, 3)
        right.addLayout(top)

        # live view + wizard
        live = QHBoxLayout()
        live.setSpacing(12)
        self.stick_l = StickCalView("LEFT STICK")
        self.stick_r = StickCalView("RIGHT STICK")
        live.addWidget(self.stick_l, 1)
        live.addWidget(self.stick_r, 1)
        side = QVBoxLayout()
        side.setSpacing(6)
        self.trig_l = TriggerCalBar("L2 / LT")
        self.trig_r = TriggerCalBar("R2 / RT")
        side.addWidget(self.trig_l)
        side.addWidget(self.trig_r)
        self.out_lbl = lab("", 11, DIM)
        self.out_lbl.setWordWrap(True)
        side.addWidget(self.out_lbl)
        side.addStretch(1)
        live.addLayout(side, 1)
        right.addLayout(live, 1)

        wiz = QFrame()
        wiz.setObjectName("wiz")
        wiz.setStyleSheet(f"QFrame#wiz {{ background: {HEAD}; border: 1px solid {BORDER}; border-radius: 3px; }}")
        wh = QHBoxLayout(wiz)
        wh.setContentsMargins(12, 8, 8, 8)
        wh.setSpacing(8)
        self.step_lbl = lab("Calibrate: measures drift, deadzone and full range for this controller in three short steps.",
                            12, SOFT)
        self.step_lbl.setWordWrap(True)
        wh.addWidget(self.step_lbl, 1)
        self.cal_btn = button("CALIBRATE", 11, 130,
                              f"padding: 7px 0; border: 1px solid {OK_BORDER}; border-radius: 3px; background: {OK_GREEN}; color: {ACCENT};",
                              f"border-color: {ACCENT}; color: {OK_TEXT};")
        self.cal_btn.clicked.connect(self._cal_button)
        wh.addWidget(self.cal_btn)
        self.cancel_cal = button("CANCEL", 11, 84,
                                 f"padding: 7px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {SOFT};",
                                 f"color: {BRIGHT};")
        self.cancel_cal.clicked.connect(self._cancel_cal)
        wh.addWidget(self.cancel_cal)
        right.addWidget(wiz)

        # values
        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        heads = ("", "CENTRE / REST", "DEADZONE", "MIN", "MAX")
        for c, t in enumerate(heads):
            grid.addWidget(slab(t, 9, LABEL, spacing=0.9), 0, c)
        self.fields = {}
        for r, k in enumerate(cp.AXES + cp.TRIGGERS, 1):
            grid.addWidget(lab(cp.AXIS_NAMES[k], 12, SOFT), r, 0)
            cols = (("center", -0.5, 0.5), ("deadzone", 0.0, cp.MAX_DEADZONE), ("min", -1.0, 0.0), ("max", 0.0, 1.0)) \
                if k in cp.AXES else (("rest", 0.0, 0.5), ("deadzone", 0.0, cp.MAX_DEADZONE), None, ("max", 0.1, 1.0))
            for c, spec in enumerate(cols, 1):
                if spec is None:
                    grid.addWidget(lab("—", 12, MUTED), r, c)
                    continue
                f, lo, hi = spec
                sb = QDoubleSpinBox()
                sb.setDecimals(3)
                sb.setSingleStep(0.01)
                sb.setRange(lo, hi)
                sb.setFont(mono(12))
                sb.setStyleSheet(SPIN_CSS)
                sb.valueChanged.connect(lambda v, k=k, f=f: self._field(k, f, v))
                self.fields[(k, f)] = sb
                grid.addWidget(sb, r, c)
        for c in range(1, 5):
            grid.setColumnStretch(c, 1)
        right.addLayout(grid)
        h.addLayout(right, 1)
        self.layout().setStretchFactor(self.body, 1)

        # footer: status ........ RESET  SAVE  CLOSE
        self.status = lab("", 11, LABEL)
        self.status.setWordWrap(True)
        self.foot_lay.addWidget(self.status, 1)
        reset = button("RESET VALUES", 11, None,
                       f"padding: 6px 10px; border: none; background: transparent; color: {LABEL};", f"color: {BRIGHT};")
        reset.setToolTip("Back to the defaults from config.py (no calibration)")
        reset.clicked.connect(self._reset_values)
        self.foot_lay.addWidget(reset)
        self.save_btn = button("SAVE", 11, 110,
                               f"padding: 6px 0; border: 1px solid {OK_BORDER}; border-radius: 3px; background: {OK_GREEN}; color: {ACCENT};",
                               f"border-color: {ACCENT}; color: {OK_TEXT};")
        self.save_btn.clicked.connect(self.save)
        self.foot_lay.addWidget(self.save_btn)
        self.close2 = button("CLOSE", 11, 84,
                             f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                             f"border-color: {ACCENT}; color: {ACCENT};")
        self.close2.clicked.connect(self.close_card)
        self.foot_lay.addWidget(self.close2)

        self.setFixedSize(1120, 690)
        self.grip = ResizeGrip(self, self.MIN_W, self.MIN_H)
        self._show_wizard()

    # ---------------- lifecycle ----------------
    def opened(self, pad_name=""):
        self.setFixedSize(*self.grip.clamp(self.width(), self.height()))
        self.pad_name = pad_name
        self._cancel_cal()
        self.reload()
        if self.profiles:
            self.list.setCurrentRow(0)
        else:
            self.new_profile()

    def reload(self, select=None):
        self.profiles = cp.load_all()
        self.list.blockSignals(True)
        self.list.clear()
        for p in self.profiles:
            self.list.addItem(QListWidgetItem(f"{p.name}\n{p.controller or '(no controller noted)'}"))
        self.list.blockSignals(False)
        if select is not None:
            names = [p.name for p in self.profiles]
            if select in names:
                self.list.blockSignals(True)
                self.list.setCurrentRow(names.index(select))
                self.list.blockSignals(False)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        g = self.grip
        g.move(self.width() - g.width() - 2, self.height() - g.height() - 2)
        g.raise_()

    def close_card(self):
        if self.dirty and self._armed != "close":
            self._arm("close", "Unsaved changes — click CLOSE again to discard them.")
            return
        self._cancel_cal()
        self._disarm()
        self._on_close()

    def key(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close_card()
            return True
        return False

    # ---------------- profile list ----------------
    def _pick(self, i):
        if not (0 <= i < len(self.profiles)):
            return
        self._cancel_cal()
        self._load(self.profiles[i].copy(), dirty=False)
        self._say(LABEL, "")

    def new_profile(self):
        self._cancel_cal()
        self.list.blockSignals(True)
        self.list.clearSelection()
        self.list.setCurrentRow(-1)
        self.list.blockSignals(False)
        self._load(cp.ControllerProfile("", self.pad_name), dirty=False)
        self._say(LABEL, "New profile — press CALIBRATE with the controller connected, then SAVE.")

    def _delete(self):
        i = self.list.currentRow()
        if not (0 <= i < len(self.profiles)):
            return
        name = self.profiles[i].name
        if self._armed != "delete":
            self._arm("delete", f'Click DELETE again to delete "{name}".')
            return
        self._disarm()
        try:
            cp.delete(name)
        except OSError as e:
            self._say(DANGER, f"Could not delete — {e}")
            return
        self.reload()
        if self.profiles:
            self.list.setCurrentRow(min(i, len(self.profiles) - 1))
        else:
            self.new_profile()
        self._say(LABEL, f'Deleted "{name}"')

    # ---------------- editing ----------------
    def _load(self, prof, dirty):
        self._loading = True
        self.edit = prof
        self.name_edit.setText(prof.name)
        self.ctrl_edit.setText(prof.controller)
        for (k, f), sb in self.fields.items():
            src = prof.axes[k] if k in cp.AXES else prof.triggers[k]
            sb.setValue(src[f])
        self._loading = False
        self.dirty = dirty

    def _edited(self, *_):
        if not self._loading:
            self.dirty = True
            self._disarm()

    def _field(self, k, f, v):
        if self._loading:
            return
        (self.edit.axes[k] if k in cp.AXES else self.edit.triggers[k])[f] = v
        self._edited()

    def _use_connected(self):
        if not self.pad_name:
            self._say(WARN, "No controller connected.")
            return
        self.ctrl_edit.setText(self.pad_name)
        self._edited()

    def _reset_values(self):
        self._cancel_cal()
        p = cp.ControllerProfile(self.name_edit.text().strip(), self.ctrl_edit.text().strip())
        self._load(p, dirty=True)
        self._say(LABEL, "Values reset to the defaults — SAVE to keep.")

    def save(self):
        name = self.name_edit.text().strip()
        if not name:
            self._say(DANGER, "Enter a profile name first.")
            self.name_edit.setFocus()
            return
        self._cancel_cal()
        self.edit.name = name
        self.edit.controller = self.ctrl_edit.text().strip()
        replaced = any(p.name == name for p in self.profiles)
        try:
            cp.save(self.edit)
        except OSError as e:
            self._say(DANGER, f"Could not save — {e}")
            return
        self.dirty = False
        self.reload(select=name)
        note = ""
        self._say(ACCENT, f'Saved "{name}"' + (" (replaced)" if replaced else "") + "." + note)

    # ---------------- calibration ----------------
    def _cal_button(self):
        if self.cal is None:
            if not self.pad_name:
                self._say(WARN, "Connect the controller first.")
                return
            self.cal = cp.Calibration()
            self.trail = {"l": [], "r": []}
            self._say(LABEL, "")
        elif self.cal.name == "ready":          # OK: start with the left stick's flicks
            self.cal.next()
        elif self.cal.stick() is not None:     # NEXT: skip the rest of this flick / rotate step
            self.cal.next()
        elif self.cal.name == "triggers":
            self.cal.next()
            warn = self.cal.warnings()
            self._load(self.cal.result(self.edit), dirty=True)
            if not self.edit.controller and self.pad_name:
                self.ctrl_edit.setText(self.pad_name)
                self.edit.controller = self.pad_name
            self.cal = None
            if warn:
                self._say(WARN, "Calibrated, but: " + "; ".join(warn) + ". Kept the old range there — "
                          "calibrate again or edit the values.")
            else:
                self._say(ACCENT, "Calibrated. Check the live view, adjust any value, then SAVE.")
        self._show_wizard()

    def _cancel_cal(self):
        if self.cal is not None:
            self.cal = None
            self._say(LABEL, "Calibration cancelled — nothing changed.")
        self.trail = {"l": [], "r": []}
        self._show_wizard()

    def _show_wizard(self):
        step = self.cal.name if self.cal is not None else None
        self.cancel_cal.setVisible(step is not None)
        self.cal_btn.setText({None: "CALIBRATE", "ready": "OK", "triggers": "FINISH"}.get(step, "NEXT"))
        self.cal_btn.setToolTip("Skip the rest of this step" if (self.cal is not None and self.cal.stick()) else "")
        if step is None:
            self.step_lbl.setText("Calibrate: measures drift, deadzone and full range for this controller in three short steps.")
        elif step in cp.Calibration.FLICK:
            c = self.cal
            flick = (f"flick it {c.arrow()} to the edge and let go" if c.phase == "push"
                     else "let go — waiting for it to settle…")
            self.step_lbl.setText(self.STEP_TEXT[step].format(flick=flick, n=c.flicks(), N=cp.Calibration.FLICKS))
        else:
            self.step_lbl.setText(self.STEP_TEXT[step].format(n=self.cal.turns(), N=cp.Calibration.TURNS))

    # ---------------- live update (menu timer, 20 Hz) ----------------
    def update_pad(self, st):
        name = st.name if st.connected else ""
        if name != self.pad_name:
            self.pad_name = name
            self.reload(select=self.edit.name if self.edit.name else None)
        self.pad_lbl.setText(f"Connected: {self.pad_name}" if self.pad_name
                             else "No controller connected — plug one in to calibrate.")
        self.pad_lbl.setStyleSheet(f"color: {LABEL if self.pad_name else WARN}; background: transparent;")
        if self.cal is not None:
            if self.cal.name in cp.Calibration.ROTATE:
                self.trail[self.cal.stick()].append((st.lx, st.ly) if self.cal.stick() == "l" else (st.rx, st.ry))
            self.cal.feed(st)                    # may move on by itself (12 flicks, 10 turns)
            self._show_wizard()                  # flick direction / counts
        e = self.edit
        c = self.cal
        name = c.name if c is not None else None
        for s, view, kx, ky in (("l", self.stick_l, "lx", "ly"), ("r", self.stick_r, "rx", "ry")):
            active = c is not None and c.stick() == s
            view.set(getattr(st, kx), getattr(st, ky), e.axes[kx], e.axes[ky], st.connected,
                     self.trail[s] if (active and name in cp.Calibration.ROTATE) else None,
                     c.target if (active and name in cp.Calibration.FLICK and c.phase == "push") else None,
                     c.settled[s] if (active and name in cp.Calibration.FLICK) else None)
        peak = self.cal.tmax if (self.cal is not None and self.cal.name == "triggers") else {}
        self.trig_l.set(st.l2, e.triggers["l2"], peak.get("l2"))
        self.trig_r.set(st.r2, e.triggers["r2"], peak.get("r2"))
        if st.connected:
            out = e.apply(st)
            dz = e.deadzones()
            f = lambda k, v: "  0.00" if abs(v) < dz[k] else f"{v:+.2f}"
            self.out_lbl.setText(f"OUTPUT (after this profile)\n"
                                 f"L  {f('lx', out.lx)}  {f('ly', out.ly)}\n"
                                 f"R  {f('rx', out.rx)}  {f('ry', out.ry)}\n"
                                 f"L2 {out.l2:.2f}   R2 {out.r2:.2f}\n"
                                 f"At rest this should read 0.00; full throw ±1.00.")
        else:
            self.out_lbl.setText("")

    # ---------------- helpers ----------------
    def _arm(self, what, msg):
        self._armed = what
        self._say(WARN, msg)
        QTimer.singleShot(4000, lambda w=what: self._disarm() if self._armed == w else None)

    def _disarm(self):
        if self._armed is not None:
            self._armed = None
            self._say(LABEL, "")

    def _say(self, color, text):
        self.status.setStyleSheet(f"color: {color}; background: transparent;")
        self.status.setText(text)


# ============================================================================
# MAIN MENU WINDOW
# ============================================================================
class MainMenu(QWidget):
    ITEMS = ("CONNECT VEHICLE", "DEMO MODE", "VIEW LOGS", "CONTROLLER MAP", "CONTROLLER PROFILES", "QUIT")

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
        self.logs_card = LogsCard(self.close_overlay)
        self.logs_ov = Overlay(self, self.logs_card, self.close_overlay)
        self.ctl_card = ControllerProfilesCard(self.close_overlay)
        self.ctl_ov = Overlay(self, self.ctl_card, self.ctl_card.close_card)
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
        elif item == "CONTROLLER PROFILES":
            self.open_overlay(self.ctl_ov)
            st = self.pad.snapshot()
            self.ctl_card.opened(st.name if st.connected else "")
        elif item == "VIEW LOGS":
            self.open_overlay(self.logs_ov)
            self.logs_card.opened()
        elif item == "QUIT":
            self.close()

    def open_overlay(self, ov):
        if self.overlay is not None:
            self.overlay.hide()
        self.overlay = ov
        ov.setGeometry(self.rect())
        ov.show()
        ov.raise_()
        if ov in (self.map_ov, self.logs_ov, self.ctl_ov):
            self.setFocus()

    def close_overlay(self):
        if self.overlay is not None:
            self.overlay.hide()
        self.overlay = None
        self.setFocus()

    def _connected(self, link, name, controller_profile=cp.NONE):
        self.close_overlay()
        self._on_connected(link, name, controller_profile=controller_profile)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        for ov in (self.connect_ov, self.map_ov, self.logs_ov, self.ctl_ov):
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
        if self.overlay is self.ctl_ov:
            if not self.ctl_card.key(e):
                super().keyPressEvent(e)
            return
        if self.overlay is self.logs_ov:
            if not self.logs_card.key(e):
                super().keyPressEvent(e)
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
        if self.overlay is self.ctl_ov:              # calibrating: the pad is input, not navigation
            self.ctl_card.update_pad(pad)
            self.prev = dict(pad.buttons)
            return
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
        elif self.overlay is self.logs_ov:          # D-pad picks a session, circle (B) closes
            if pressed("circle"):
                self.close_overlay()
            if pressed("up"):
                self.logs_card.step(-1)
            if pressed("down"):
                self.logs_card.step(1)
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