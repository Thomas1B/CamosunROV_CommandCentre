"""Main console window: layout, arming, failsafes, event log and control loop.

Opened from the main menu with a live Link (or DemoLink). Closing it returns to the
main menu - but only once the thrusters are disarmed.
"""

import html
import math
import time
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QTextEdit,
                               QVBoxLayout, QWidget)

from command_center_py.config import (APP_VERSION, RATE_HZ, GAIN_STEPS, DEFAULT_GAIN_INDEX, TILT_MIN,
                        TILT_MAX, TILT_STEP, ARM_HOLD_S, ZERO_HOLD_S, REQUIRE_LINK_TO_ARM,
                        THRUSTERS, LOSS_PRINT_S, VIDEO_PORT, VIDEO_STALE_S, DEMO_SIM_PAD)
from command_center_py.demo_pad import DemoPad
from command_center_py.mixer import mix
from command_center_py.video import VideoReceiver
from command_center_py.ui.theme import (BG, PANEL, HEAD, BORDER, BORDER2, TEXT, BRIGHT, MUTED, DIM,
                          LABEL, ACCENT, WARN, DANGER, BLUE, SANS, VALUE_PX, UNIT_PX, fs, mono, lab)
from command_center_py.ui.reference_fields import ReferenceDialog
from command_center_py.ui.widgets import (BipolarBar, TriggerBar, StickView, VideoPane, LevelBarSOC,
                            SectionHeader, ThrusterRow, Chip, MetricCard, StatusRow,
                            ControllerMapDialog, CONTROLLER_MAPS, LAYOUT)


CARDINALS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


class ConsoleWindow(QMainWindow):
    closed = Signal()        # emitted once the console has shut down (back to the main menu)

    def __init__(self, link, pad, demo=False, vehicle=""):
        """link: an open Link / DemoLink (the console closes it on exit).
        pad: the shared Gamepad (owned by the app, not closed here)."""
        super().__init__()
        self.setWindowTitle("Camosun ROV — Control Console"
                            + (" — DEMO" if demo else (f" — {vehicle}" if vehicle else "")))
        self.resize(1440, 900)
        self.setMinimumSize(1200, 760)

        self.demo = demo
        self.vehicle = vehicle
        self.link = link
        # demo mode: a simulated controller drives the vehicle until a real one is plugged in
        self.pad = DemoPad(pad, lambda: self.armed) if (demo and DEMO_SIM_PAD) else pad
        self._force_close = False
        self._done = False
        self.notice = ""
        self.notice_until = 0.0
        self.kind = None               # "ds3" or "xbox" - picked with the toggle above STICK INPUT
        self.k = CONTROLLER_MAPS["ds3"]  # button names for the current layout

        self.armed = False
        self.tilt = 0
        self.gain_idx = DEFAULT_GAIN_INDEX
        self.throttles = [0] * 6
        self.tel = {}
        self.prev_buttons = {}
        self.arm_hold_start = None
        self.tare = None                 # depth (m) taken as zero, or None = true depth (display only)
        self.zero_hold_start = None
        self.repeat_at = {}
        self.was_connected = False
        self.was_linked = False
        self.temp_warned = False
        self.leak_alarmed = False
        self.temp_warned = False
        self.leak_alarmed = False

        self._build_ui()
        self._apply_kind(LAYOUT["kind"])

        # Live camera (not in demo mode - there is no camera to listen to).
        self.video_rx = None
        self._video_id = 0
        self._video_last_new = 0.0
        self._video_was_live = False
        if demo:
            self.video.set_video(None, False, "demo mode - no camera")
        else:
            self.video_rx = VideoReceiver(getattr(link, "video_port", VIDEO_PORT))
        self.log("SYS", f"Console v{APP_VERSION} started" + (" in DEMO mode" if self.demo
                                                             else f" — {self.vehicle} @ {self.link.label}"), BLUE)
        self.log("CFG", f"Reference values — {self.link.refs.summary()}", ACCENT)
        self._refs_ack_logged = False
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
        self.loss_timer = QTimer(self)
        self.loss_timer.timeout.connect(self.print_lost_packets)
        self.loss_timer.start(LOSS_PRINT_S * 1000)

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
        f.setPixelSize(fs(13))
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
        title = lab("SUBSEA ROV CONSOLE", fs(11), ACCENT, QFont.Weight.Bold)
        title.setContentsMargins(8, 0, 12, 0)
        mb.setCornerWidget(title, Qt.Corner.TopLeftCorner)
        m = mb.addMenu("File")
        m.addAction("Reference Values…", self.show_reference_values)
        m.addAction("Back to Main Menu", self.close)
        m = mb.addMenu("Vehicle")
        a = QAction("Arm / Disarm", self)
        a.triggered.connect(self.toggle_arm_click)
        m.addAction(a)
        a = QAction("E-STOP\tSpace", self)
        a.triggered.connect(lambda: self.estop("menu"))
        m.addAction(a)
        m = mb.addMenu("Help")
        m.addAction("Dualshock3 Map", lambda: self.show_controller_map("ds3"))
        m.addAction("Xbox Map", lambda: self.show_controller_map("xbox"))

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
        self.link_lbl = lab("LINK DOWN", fs(11), TEXT, QFont.Weight.DemiBold)
        lh.addWidget(self.link_lbl)
        lh.addWidget(lab(self.link.label, fs(11), MUTED))
        h.addWidget(link)

        stats = QFrame()
        stats.setObjectName("pill")
        stats.setStyleSheet(pill_css)
        sh = QHBoxLayout(stats)
        sh.setContentsMargins(11, 5, 11, 5)
        self.stats_lbl = QLabel()
        self.stats_lbl.setFont(mono(fs(11)))
        sh.addWidget(self.stats_lbl)
        h.addWidget(stats)

        clock = QFrame()                     # local time, in its own pill
        clock.setObjectName("pill")
        clock.setStyleSheet(pill_css)
        ch = QHBoxLayout(clock)
        ch.setContentsMargins(11, 5, 11, 5)
        self.clock_lbl = QLabel()
        self.clock_lbl.setFont(mono(fs(11)))
        ch.addWidget(self.clock_lbl)
        h.addWidget(clock)

        h.addStretch(1)
        self.pad_lbl = QLabel()
        self.pad_lbl.setFont(mono(fs(11)))
        h.addWidget(self.pad_lbl)

        self.arm_btn = QPushButton("DISARMED")
        self.arm_btn.setFont(mono(fs(12), QFont.Weight.Bold))
        self.arm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.arm_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.arm_btn.setMinimumWidth(fs(150))
        self.arm_btn.clicked.connect(self.toggle_arm_click)
        h.addWidget(self.arm_btn)
        self._arm_style = None

        es = QPushButton("E-STOP")
        es.setFont(mono(fs(12), QFont.Weight.Bold))
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
        # leave 1 px free on the bordered side, or section headers / the telemetry grid
        # (which paint their own backgrounds) cover the panel's vertical border
        v.setContentsMargins(1 if side == "left" else 0, 0, 1 if side == "right" else 0, 0)
        v.setSpacing(0)
        return f, v

    def _build_left(self):
        outer, ov = self._panel(fs(272), "right")
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
        gain.addWidget(lab("GAIN", fs(11), DIM))
        self.gain_lbl = lab("50 %", fs(11), DIM, QFont.Weight.Bold)
        gain.addWidget(self.gain_lbl)
        gain.addStretch(1)
        self.gain_hint = lab("", fs(10), MUTED)
        gain.addWidget(self.gain_hint)
        tv.addLayout(gain)
        v.addWidget(tw)
        v.addWidget(self._hline()) 

        cw2 = QWidget()
        cv = QVBoxLayout(cw2)
        cv.setContentsMargins(12, 10, 12, 10)
        cv.setSpacing(6)
        top = QHBoxLayout()
        top.addWidget(lab("Camera Tilt", fs(11), DIM))
        top.addStretch(1)
        self.tilt_lbl = lab("+0°", fs(16), TEXT, QFont.Weight.Bold)
        top.addWidget(self.tilt_lbl)
        cv.addLayout(top)
        self.tilt_bar = BipolarBar(10)
        cv.addWidget(self.tilt_bar)
        ends = QHBoxLayout()
        ends.addWidget(lab(f"DOWN {TILT_MIN}°", fs(9), MUTED))
        ends.addStretch(1)
        ends.addWidget(lab(f"UP +{TILT_MAX}°", fs(9), MUTED))
        cv.addLayout(ends)
        cv.addWidget(lab(f"D-pad ↑↓ · {TILT_STEP}° per step · hold to repeat", fs(10), MUTED))
        v.addWidget(cw2)

        # controller toggle: DUALSHOCK 3 | XBOX - changes the button labels only
        # (SDL reads both pads with the same layout, so driving is identical)
        v.addWidget(self._hline())        # divider between GAIN and CONTROLLER
        tgw = QWidget()
        th = QHBoxLayout(tgw)
        th.setContentsMargins(12, 10, 12, 10)
        th.setSpacing(0)
        th.addWidget(lab("CONTROLLER", fs(11), DIM))
        th.addStretch(1)
        self.layout_btns = {}
        for kind, text, side in (("ds3", "DUALSHOCK 3", "left"), ("xbox", "XBOX", "right")):
            b = QPushButton(text)
            b.setFont(mono(fs(10), QFont.Weight.DemiBold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)    # keep SPACE = E-STOP working
            b.setFixedHeight(fs(22))
            b.setProperty("side", side)
            b.clicked.connect(lambda _=False, k=kind: self.set_layout(k))
            self.layout_btns[kind] = b
            th.addWidget(b)
        v.addWidget(tgw)

        self.stick_hdr = SectionHeader("STICK INPUT", "DUALSHOCK 3", top_border=True)
        v.addWidget(self.stick_hdr)
        sw = QWidget()
        sg = QGridLayout(sw)
        sg.setContentsMargins(12, 10, 12, 10)
        sg.setHorizontalSpacing(12)
        sg.setVerticalSpacing(4)
        self.stick_l, self.stick_r = StickView(), StickView(x_only=True)
        sg.addWidget(self.stick_l, 0, 0, Qt.AlignmentFlag.AlignHCenter)
        sg.addWidget(self.stick_r, 0, 1, Qt.AlignmentFlag.AlignHCenter)
        sg.addWidget(lab("L · FWD/BACK + SIDE", fs(9), MUTED, align=Qt.AlignmentFlag.AlignHCenter), 1, 0)
        sg.addWidget(lab("R · ROTATE (YAW)", fs(9), MUTED, align=Qt.AlignmentFlag.AlignHCenter), 1, 1)
        v.addWidget(sw)

        trw = QWidget()
        tg = QGridLayout(trw)
        tg.setContentsMargins(12, 5, 12, 10)
        tg.setHorizontalSpacing(8)
        tg.setVerticalSpacing(4)
        self.l2_bar, self.r2_bar = TriggerBar(BLUE), TriggerBar(ACCENT)
        self.l2_lbl, self.r2_lbl = lab("", fs(9), MUTED), lab("", fs(9), MUTED)
        tg.addWidget(self.l2_lbl, 0, 0)
        tg.addWidget(self.r2_lbl, 0, 1)
        tg.addWidget(self.l2_bar, 1, 0)
        tg.addWidget(self.r2_bar, 1, 1)
        v.addWidget(trw)

        cw = QWidget()
        cg = QGridLayout(cw)
        cg.setContentsMargins(12, 0, 12, 12)
        cg.setSpacing(4)
        self.chips = {}
        chip_layout = ["cross", "circle", "square", "triangle", "l1", "r1", "l2", "r2",
                       "select", "start", "ps", "dpad"]
        for i, key in enumerate(chip_layout):
            c = Chip("")      # text set by _apply_kind() for the connected controller
            self.chips[key] = c
            cg.addWidget(c, i // 4, i % 4)
        v.addWidget(cw)

        

        v.addStretch(1)

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
        logf.setFixedHeight(150)
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
        hh.addWidget(lab("EVENT LOG", fs(10), LABEL, QFont.Weight.Bold))
        hh.addWidget(lab(f"· command stream {RATE_HZ} Hz", fs(10), MUTED))
        hh.addStretch(1)
        lv.addWidget(hdr)
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(mono(fs(11)))
        self.log_view.document().setMaximumBlockCount(300)
        self.log_view.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.log_view.setStyleSheet(f"QTextEdit {{ background: {PANEL}; border: none; color: {DIM}; padding: 4px 8px; }}")
        lv.addWidget(self.log_view)
        v.addWidget(logf)
        return w

    def _build_right(self):
        outer, v = self._panel(fs(268), "left")
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
            card = MetricCard(name, self.refresh_units,
                              on_zero=(lambda: self.toggle_zero("console button")) if key == "depth" else None)
            self.metrics[key] = card
            g.addWidget(card, i // 2, i % 2)
        v.addWidget(grid)
        v.addWidget(self._hline())

        imu = QWidget()
        iv = QVBoxLayout(imu)
        iv.setContentsMargins(12, 12, 12, 12)
        iv.setSpacing(8)
        iv.addWidget(lab("IMU ATTITUDE", fs(10), LABEL, QFont.Weight.Bold))

        # heading: same row layout as ROLL / PITCH / YAW ("HEADING ....... 214°  SW"), no bar,
        # with a divider underneath
        hrow = QHBoxLayout()
        hrow.setSpacing(20)
        hrow.addWidget(lab("HEADING", fs(11), DIM), 0, Qt.AlignmentFlag.AlignBaseline)
        hrow.addStretch(1)
        self.heading_lbl = lab("--", VALUE_PX, BRIGHT, QFont.Weight.Bold)
        hrow.addWidget(self.heading_lbl, 0, Qt.AlignmentFlag.AlignBaseline)
        self.cardinal_lbl = lab("", VALUE_PX, BRIGHT, QFont.Weight.Bold)
        hrow.addWidget(self.cardinal_lbl, 0, Qt.AlignmentFlag.AlignBaseline)
        iv.addLayout(hrow)
        iv.addWidget(self._hline())

        self.imu_rows = {}
        for key in ("ROLL", "PITCH", "YAW"):
            top = QHBoxLayout()
            top.addWidget(lab(key, fs(11), DIM), 0, Qt.AlignmentFlag.AlignBaseline)
            top.addStretch(1)
            val = lab("--", VALUE_PX, BRIGHT, QFont.Weight.Bold)
            top.addWidget(val, 0, Qt.AlignmentFlag.AlignBaseline)
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
        pv.addWidget(lab("BATTERY", fs(9), MUTED))
        self.volt_lbl = QLabel("--")
        self.volt_lbl.setFont(mono(VALUE_PX, QFont.Weight.Bold))
        pv.addWidget(self.volt_lbl)
        self.soc_bar = LevelBarSOC()
        pv.addWidget(self.soc_bar)
        v.addWidget(pw)
        v.addWidget(self._hline())

        sw = QWidget()
        sv = QVBoxLayout(sw)
        sv.setContentsMargins(12, 12, 12, 12)
        sv.setSpacing(6)
        sv.addWidget(lab("SYSTEM STATUS", fs(10), LABEL, QFont.Weight.Bold))
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
        sb.setFixedHeight(fs(24))
        sb.setSizeGripEnabled(False)
        self.msg_lbl = lab("", fs(10), DIM)
        self.msg_lbl.setContentsMargins(10, 0, 0, 0)
        sb.addWidget(self.msg_lbl, 1)
        self.tx_lbl = lab("", fs(10), MUTED)
        self.rx_lbl = lab("", fs(10), MUTED)
        self.lost_lbl = lab("", fs(10), MUTED)      # command packets that never reached the Pi
        ver = lab(f"v{APP_VERSION}", fs(10), MUTED)
        ver.setContentsMargins(0, 0, 12, 0)          # keep the version off the window edge
        for w in (self.tx_lbl, self.rx_lbl, self.lost_lbl, ver):
            sb.addPermanentWidget(w)

    # ---------------- actions ----------------
    def log(self, tag, msg, color=ACCENT):
        t = datetime.now().strftime("%H:%M:%S")
        tagp = html.escape(tag).ljust(5).replace(" ", "&nbsp;")
        self.log_view.append(f'<span style="color:#4d5d6d">{t}</span>&nbsp;&nbsp;'
                             f'<span style="color:{color}; font-weight:600">{tagp}</span>&nbsp;'
                             f'<span style="color:{DIM}">{html.escape(msg)}</span>')

    def try_arm(self, source):
        now = time.monotonic()
        pad = self.pad.snapshot()
        if not pad.connected:                # arming needs a controller; disarming / E-STOP never do
            self.log("DENY", "Arm refused — no controller connected", WARN)
            return
        if max(abs(pad.lx), abs(pad.ly), abs(pad.rx), abs(pad.ry)) > 0.15:
            self.log("DENY", "Arm refused — centre both sticks first", WARN)
            return
        if max(pad.l2, pad.r2) > 0.15:
            self.log("DENY", f"Arm refused — release {self.k['l2']} and {self.k['r2']} first", WARN)
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

    def toggle_zero(self, source):
        """Depth zero (tare). Display only: the reference values, Pi and STM32 keep true depth,
        so auto depth control and limits are unaffected. Cleared when this console window closes."""
        if self.tare is None:
            d = self._num("depth_m")
            if d is None:
                self.log("DENY", "Can't zero depth — no depth reading yet", WARN)
                return
            self.tare = d
            self.log("DEPTH", f"Depth zeroed at {d:.2f} m ({source})", WARN)
        else:
            self.tare = None
            self.log("DEPTH", f"Depth zero cleared — showing true depth ({source})", MUTED)
        self._update_metrics()

    def refresh_units(self):
        self._update_metrics()

    def set_layout(self, kind):
        """Toggle clicked: switch the button labels and remember it for the main menu."""
        if kind == self.kind:
            return
        LAYOUT["kind"] = kind
        self._apply_kind(kind)
        self.log("PAD", f"Button labels set to {self.k['short']}", ACCENT)

    def _apply_kind(self, kind):
        """Relabel every controller-specific label for a DualShock 3 ("ds3") or Xbox ("xbox") pad."""
        if kind == self.kind:
            return
        self.kind = kind
        k = self.k = CONTROLLER_MAPS[kind]
        for name, b in self.layout_btns.items():
            on = name == kind
            r = "border-top-left-radius: 3px; border-bottom-left-radius: 3px;" if b.property("side") == "left" \
                else "border-top-right-radius: 3px; border-bottom-right-radius: 3px; border-left: none;"
            if on:
                b.setStyleSheet(f"QPushButton {{ padding: 0 10px; border: 1px solid #2a6f5c; {r}"
                                f" background: #123a30; color: {ACCENT}; }}")
            else:
                b.setStyleSheet(f"QPushButton {{ padding: 0 10px; border: 1px solid {BORDER2}; {r}"
                                f" background: {HEAD}; color: #7c8b9c; }}"
                                f"QPushButton:hover {{ color: {BRIGHT}; }}")
        self.stick_hdr.right.setText(k["short"])
        self.gain_hint.setText(f"{k['l1']} ▼  {k['r1']} ▲")
        self.l2_lbl.setText(f"{k['l2']} · DESCEND")
        self.r2_lbl.setText(f"{k['r2']} · ASCEND")
        chip_text = {"cross": k["cross"], "circle": k["circle"], "square": k["sq"], "triangle": k["tri"],
                     "l1": k["l1"], "r1": k["r1"], "l2": k["l2"], "r2": k["r2"],
                     "select": k["sel"], "start": k["start"], "ps": k["ps"], "dpad": "↑↓"}
        for key, chip in self.chips.items():
            chip.setText(chip_text[key])

    def show_reference_values(self):
        """File > Reference Values...: edit the Bar30 reference values and send them to the Pi."""
        dlg = ReferenceDialog(self, self.link.refs, scale=fs(100) / 100)
        if dlg.exec() and dlg.result_refs is not None:
            if dlg.result_refs == self.link.refs:
                return
            self.link.set_refs(dlg.result_refs)
            self._refs_ack_logged = False
            self.log("CFG", f"Reference values — {dlg.result_refs.summary()} (sending to Pi)", ACCENT)

    def show_controller_map(self, kind="ds3"):
        ControllerMapDialog(self, kind, ARM_HOLD_S, scale=fs(100) / 100).exec()

    # ---------------- control loop ----------------
    def tick(self):
        now = time.monotonic()
        pad = self.pad.snapshot()
        self._handle_pad(pad, now)
        self.throttles = self._mix(pad) if (self.armed and pad.connected) else [0] * 6
        self.link.send(self.armed, self.throttles, self.tilt)
        self.link.service_refs(now)          # reference values -> Pi, resent until acknowledged
        tel = self.link.poll()
        if tel:
            self.tel.update(tel)
        self._failsafes(now)

    def print_lost_packets(self):
        """Every LOSS_PRINT_S seconds, print lost command packets (laptop -> Pi) to the terminal."""
        stamp = datetime.now().strftime("%H:%M:%S")
        counts = self.link.take_lost()
        if counts is None:
            print(f"[{stamp}] Packets lost: unknown - no ack/rx_cmds from the Pi yet", flush=True)
            return
        lost, sent = counts
        print(f"[{stamp}] {lost} packets lost in the past {LOSS_PRINT_S} seconds, {lost}/{sent}", flush=True)

    def refresh_ui(self):
        self._refresh(self.pad.snapshot(), time.monotonic())

    def _handle_pad(self, pad, now):
        if pad.connected and not self.was_connected:
            self.log("PAD", f"Controller connected — {pad.name} [{pad.mode}]", ACCENT)
        if not pad.connected and self.was_connected:
            self.log("PAD", "Controller disconnected", WARN)
            self.disarm("controller lost", "FAIL", WARN)
            self.arm_hold_start = None
            self.zero_hold_start = None
        self.was_connected = pad.connected
        if not pad.connected:
            self.prev_buttons = {}
            return

        prev = self.prev_buttons
        pressed = lambda b: pad.down(b) and not prev.get(b)

        if pressed("select") or pressed("ps"):
            self.estop("controller " + (self.k["sel"] if pad.down("select") else self.k["ps"]))

        if pressed("start"):
            if self.armed:
                self.disarm(self.k["start"])
            else:
                self.arm_hold_start = now
        if not pad.down("start"):
            self.arm_hold_start = None
        elif self.arm_hold_start is not None and not self.armed and now - self.arm_hold_start >= ARM_HOLD_S:
            self.arm_hold_start = None
            self.try_arm(f"{self.k['start']} held")

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
        if pressed("cross"):                 # hold CROSS / A to zero depth, hold again to clear
            self.zero_hold_start = now
        if not pad.down("cross"):
            self.zero_hold_start = None
        elif self.zero_hold_start is not None and now - self.zero_hold_start >= ZERO_HOLD_S:
            self.zero_hold_start = None
            self.toggle_zero(f"{self.k['cross']} held")
        if pressed("square"):
            d = self._num("depth_m")
            rel = f" (rel {d - self.tare:.2f} m)" if (d is not None and self.tare is not None) else ""
            self.log("MARK", "Operator mark" + (f" @ {d:.2f} m{rel}" if d is not None else ""), BLUE)

        self.prev_buttons = dict(pad.buttons)

    def _step_tilt(self, d):
        new = max(TILT_MIN, min(TILT_MAX, self.tilt + d * TILT_STEP))
        if new != self.tilt:
            self.tilt = new
            self.log("CAM", f"Camera tilt {new:+d}°", BLUE)

    def _mix(self, pad):
        return mix(pad, GAIN_STEPS[self.gain_idx])

    def _failsafes(self, now):
        if self.link.refs_acked() and not self._refs_ack_logged:
            self._refs_ack_logged = True
            self.log("CFG", "Reference values applied by the Pi", ACCENT)
        elif not self.link.refs_acked() and self._refs_ack_logged:
            self._refs_ack_logged = False    # Pi restarted / lost them - they are being resent
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
        d, p, wt, it = (self._num(k) for k in ("depth_m", "pressure_kpa", "water_c", "internal_c"))
        f = lambda v, fmt: "--" if v is None else format(v, fmt)
        c2f = lambda c: None if c is None else c * 9 / 5 + 32
        dc = self.metrics["depth"]
        rd = None if d is None else (d - self.tare if self.tare is not None else d)   # zeroed depth
        dc.set(f(rd, ".1f"), "m", f(None if rd is None else rd * 3.28084, ".1f"), "ft")
        self.metrics["pressure"].set(f(p, ".1f"), "kPa", f(None if p is None else p * 0.145038, ".1f"), "psi")
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
            f'<span style="color:{MUTED}">RATE </span><b style="color:{TEXT}">{RATE_HZ}</b><span style="color:{MUTED}"> Hz</span>{sep}'
            f'<span style="color:{MUTED}">RTT </span><b style="color:{TEXT}">{rtt}</b><span style="color:{MUTED}"> ms</span>{sep}'
            f'<span style="color:{MUTED}">LOSS </span><b style="color:{TEXT}">{loss}</b><span style="color:{MUTED}"> %</span>')
        self.clock_lbl.setText(f'<b style="color:#7fd9c0">{datetime.now().strftime("%H:%M:%S")}</b>'
                               f'<span style="color:{MUTED}"> LOCAL</span>')
        if pad.connected:
            # Show the configured layout, not the driver's device name (DsHidMini can make
            # a DualShock 3 report itself as an Xbox pad). The real name is in the event log.
            self.pad_lbl.setText(f'<span style="color:#7c8b9c">GAMEPAD </span>'
                                 f'<b style="color:{ACCENT}">{self.k["short"]} OK</b>'
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
        if yaw is None:
            self.heading_lbl.setText("--")
            self.cardinal_lbl.setText("")
        else:
            hdg = yaw % 360
            self.heading_lbl.setText(f"{hdg:03.0f}°")
            self.cardinal_lbl.setText(CARDINALS[int(round(hdg / 22.5)) % 16])
        v = self._num("voltage")
        self.volt_lbl.setText(f'<span style="color:{BRIGHT}">{"--" if v is None else f"{v:.2f}"}</span>'
                              f'<span style="font-size:{UNIT_PX}px; color:{MUTED}; font-weight:500"> V</span>')
        soc = None if v is None else max(0, min(100, round((v - 13.2) / (16.8 - 13.2) * 100)))  # 4S Li-ion guess
        self.soc_bar.set(soc or 0)

        leak = self.tel.get("leak")
        if not linked or leak is None:
            self.st_leak.set("NO DATA", MUTED)
        else:
            self.st_leak.set("LEAK" if leak else "DRY", DANGER if leak else ACCENT)
        self.st_link.set("UP" if linked else "DOWN", ACCENT if linked else DANGER)
        self.st_pad.set(("OK" if pad.mode == "SDL" else "RAW") if pad.connected else "MISSING",
                        (ACCENT if pad.mode == "SDL" else WARN) if pad.connected else DANGER)
        self.st_cmd.set(f"{RATE_HZ} Hz", TEXT)

        # video frame + HUD
        self._update_video(now)
        zh = 0.0
        if self.zero_hold_start is not None:
            zh = min(1.0, (now - self.zero_hold_start) / ZERO_HOLD_S)
        self.metrics["depth"].set_zero(self.tare is not None, zh, self.k["cross"])
        imp = self.metrics["depth"].imperial
        d = self._num("depth_m")
        if d is not None and self.tare is not None:
            d -= self.tare                   # HUD shows the same (zeroed) depth as the card
        self.video.set_state(
            roll=roll or 0.0, pitch=pitch or 0.0, heading=yaw or 0.0,
            depth=None if d is None else (d * 3.28084 if imp else d), depth_unit="ft" if imp else "m",
            armed=self.armed, arm_progress=hold, gain=GAIN_STEPS[self.gain_idx], tilt=self.tilt,
            start_btn=self.k["start"])

        # status bar
        if now < self.notice_until:
            self.msg_lbl.setText(self.notice)
        elif self.armed:
            self.msg_lbl.setText(f"Armed — streaming control frames at {RATE_HZ} Hz")
        elif not pad.connected:
            self.msg_lbl.setText(f"Connect a {self.k['short'].title().replace('Dualshock', 'DualShock')} to drive — see Help")
        else:
            self.msg_lbl.setText(f"Controller ready — hold {self.k['start']} {ARM_HOLD_S:.0f} s to arm")
        self.tx_lbl.setText(f"TX {self.link.tx_count:,} pkt   │")
        self.rx_lbl.setText(f"RX {self.link.rx_count:,} pkt   │")
        lost = self.link.lost_total          # None until the Pi has reported ack / rx_cmds
        self.lost_lbl.setText(f"LOST {'--' if lost is None else f'{lost:,}'} pkt   │")

    def _update_video(self, now):
        if self.video_rx is None:
            return
        img, fid, status = self.video_rx.latest()
        if fid != self._video_id:
            self._video_id = fid
            self._video_last_new = now
        live = img is not None and now - self._video_last_new < VIDEO_STALE_S
        if live and not self._video_was_live:
            self.log("VIDEO", f"Camera stream {status}", ACCENT)
        elif self._video_was_live and not live:
            self.log("VIDEO", "Camera stream lost", WARN)
        self._video_was_live = live
        self.video.set_video(img, live, status)

    def closeEvent(self, e):
        # Never leave the console with live thrusters: closing is refused while armed.
        # (Ctrl+C in the terminal uses force_close(), which disarms first.)
        if self.armed and not self._force_close:
            e.ignore()
            self.log("DENY", f"Disarm the ROV before leaving the console (tap {self.k['start']} or click ARMED)", WARN)
            self.notice = "Disarm the ROV before leaving the console"
            self.notice_until = time.monotonic() + 4.0
            return
        if not self._done:
            self._done = True
            self.timer.stop()
            self.ui_timer.stop()
            self.loss_timer.stop()
            if self.video_rx is not None:
                self.video_rx.stop()      # frees the UDP video port for the next session
            self.armed = False
            for _ in range(3):   # make sure the Pi sees a disarmed frame on exit
                self.link.send(False, [0] * 6, self.tilt)
            self.link.close()
            self.closed.emit()
        super().closeEvent(e)

    def force_close(self):
        """Disarm, send zero frames and close even if armed (Ctrl+C / program exit)."""
        self.armed = False
        self._force_close = True
        self.close()