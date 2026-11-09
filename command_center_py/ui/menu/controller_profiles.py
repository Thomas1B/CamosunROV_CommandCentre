"""CONTROLLER PROFILES card: calibrate a controller (drift, deadzone, range) and save it.

Also the two live gauges it draws (StickCalView, TriggerCalBar)."""

import math

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget)

from command_center_py.controller import profiles as cp
from command_center_py.ui.menu.cards import (Card, EDIT_CSS, LIST_CSS, OK_BORDER, OK_GREEN,
                                             OK_TEXT, ResizeGrip, SOFT, SPIN_CSS, button, slab)
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, DIM, GRID, HEAD,
                                        LABEL, MUTED, WARN, WELL, lab, mono)


class ControllerProfilesCard(Card):
    """CONTROLLER PROFILES: calibrate a controller and save it as a profile.

    Left: saved profiles, NEW, DELETE.
    Right: name + controller it belongs to, live stick and trigger views, the CALIBRATE wizard
    (REST -> ROTATE -> TRIGGERS) and every value as an editable field. SAVE writes
    controller_profiles/<name>.json. Mouse / keyboard only: the controller is being
    calibrated, so its buttons don't operate this page. Esc or CLOSE closes it.
    """

    MIN_W, MIN_H = 900, 560
    # the counts use non-breaking spaces (\u00a0) so "3 / 20 flicks" always wraps as one piece
    STEP_TEXT = {
        "ready": "Hands off both sticks and both triggers, then press OK to start.",
        "left_flick": "LEFT STICK — {flick}   {n}\u00a0/\u00a0{N}\u00a0flicks",
        "left_cw": "LEFT STICK — push it to the edge and rotate CLOCKWISE.   {n}\u00a0/\u00a0{N}\u00a0turns",
        "left_ccw": "LEFT STICK — now rotate COUNTER-CLOCKWISE.   {n}\u00a0/\u00a0{N}\u00a0turns",
        "right_flick": "RIGHT STICK — {flick}   {n}\u00a0/\u00a0{N}\u00a0flicks",
        "right_cw": "RIGHT STICK — push it to the edge and rotate CLOCKWISE.   {n}\u00a0/\u00a0{N}\u00a0turns",
        "right_ccw": "RIGHT STICK — now rotate COUNTER-CLOCKWISE.   {n}\u00a0/\u00a0{N}\u00a0turns",
        "triggers": "TRIGGERS — press L2 and R2 (LT / RT) all the way down, release, then press FINISH.",
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
        wh.setContentsMargins(12, 14, 8, 14)   # 14 px top/bottom: the bar is 25 % taller than with 8 px (59 vs 47 px)
        wh.setSpacing(8)
        self.step_lbl = lab("Calibration measures drift, deadzone and full range for this controller in three short steps.",
                            15, SOFT)   # 25 % larger than the 12 px body text, so the instructions stand out
        self.step_lbl.setWordWrap(True)
        self.step_lbl.setContentsMargins(0, 0, 32, 0)   # wrap 40 px before the buttons (32 + the 8 px spacing)
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
            self.step_lbl.setText("Calibration measures drift, deadzone and full range for this controller in three short steps.")
        elif step in cp.Calibration.FLICK:
            c = self.cal
            flick = (f"flick it {c.arrow()} to the edge and let go." if c.phase == "push"
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
            self.cal.feed(st)                    # may move on by itself (20 flicks, 10 turns)
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
