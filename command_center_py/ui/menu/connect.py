"""CONNECT VEHICLE card: vehicle name / saved profile, Pi IP, ports, reference values,
controller profile; CONNECT waits for the Pi to answer before opening the console."""

import re
import time

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from command_center_py.config import (CMD_PORT, CONNECT_TIMEOUT_S, DEFAULT_VEHICLE_NAME, PI_HOST,
                                      RATE_HZ, TELEM_PORT, VIDEO_PORT)
from command_center_py.controller import profiles as cp
from command_center_py.ui.console.reference_dialog import RefFields
from command_center_py.ui.menu.cards import (Card, OK_BORDER, OK_GREEN, OK_TEXT, RED_BORDER,
                                             RED_DOT, SOFT, button, slab, spaced)
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, GRID, HEAD, LABEL,
                                        MUTED, WELL, combo_arrow_css, lab, mono)
from command_center_py.vehicle import profiles
from command_center_py.vehicle.link import Link, check_ipv4, check_port


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
        "connecting": ("Connecting to {ip} · cmd {cmd} · {left:.0f} s…  (Esc to stop)", "#ffd479", "#ffd479"),
        "timeout":    ("No answer from {ip} — check tether and power", DANGER, RED_DOT),
        "cancelled":  ("Connection attempt cancelled", LABEL, MUTED),
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
        self.ref_fields = RefFields(self.SCALE, label_color=BRIGHT, readable_units=True, tab_focus=True)
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

        # Tab / Shift+Tab go through every control, top to bottom, and wrap round inside
        # the dialog. Space or Enter presses the focused button (see eventFilter); Enter
        # anywhere else does nothing, so it only connects when CONNECT has the focus.
        self.cancel_btn = cancel
        rf = self.ref_fields
        self.tab_chain = [self.name_edit, self.profile_box, self.ip_edit, self.cmd_edit, self.tel_edit,
                          self.vid_edit, rf.surface_edit, rf.unit_box, rf.density_edit, rf.on_btn, rf.off_btn,
                          self.ctl_box, self.save_btn, self.del_btn, cancel, self.conn_btn, self.close_btn]
        ring = f"QPushButton:focus {{ border: 1px solid {ACCENT}; }}"
        for b in (self.save_btn, self.del_btn, cancel, self.conn_btn, self.close_btn):
            b.setFocusPolicy(Qt.FocusPolicy.TabFocus)
            b.setAutoDefault(False)
            b.setStyleSheet(b.styleSheet() + ring)
            b.installEventFilter(self)

        self.profiles = []
        self.reload_profiles()
        self.reload_controller_profiles()
        self._refresh()

    def eventFilter(self, obj, e):
        """Enter / Return on a focused footer button (or ✕) presses it, like Space."""
        if (e.type() == QEvent.Type.KeyPress and e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and isinstance(obj, QPushButton) and obj.isEnabled()):
            obj.click()
            return True
        return super().eventFilter(obj, e)

    def focusNextPrevChild(self, nxt):
        """Tab order inside the dialog (skips anything disabled), wrapping at both ends."""
        chain = [w for w in self.tab_chain if w.isVisible() and w.isEnabled()]
        if not chain:
            return False
        cur = self.focusWidget()
        i = chain.index(cur) if cur in chain else (-1 if nxt else 0)
        chain[(i + (1 if nxt else -1)) % len(chain)].setFocus(Qt.FocusReason.TabFocusReason)
        return True

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

    def stop_attempt(self):
        """Esc while connecting: stop trying, but keep the dialog open to edit and retry."""
        self.abort_attempt()
        self._set("cancelled")
        self.conn_btn.setFocus(Qt.FocusReason.OtherFocusReason)   # Enter on it tries again

    def key(self, e):
        # Esc while connecting stops the attempt and keeps the dialog open; otherwise Esc
        # closes the dialog. Enter only acts on the focused button (eventFilter): there is no
        # "Enter anywhere = CONNECT", because connecting starts sending command packets to the ROV.
        if e.key() == Qt.Key.Key_Escape:
            if self.state == "connecting":
                self.stop_attempt()
            else:
                self.cancel()
            return True
        return False
