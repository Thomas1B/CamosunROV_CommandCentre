"""Main menu: the first screen of the command centre (from the ROV Main Menu design).

    CONNECT VEHICLE ... dialog: vehicle name / saved profile, Pi IP, ports. CONNECT
                        listens for telemetry for CONNECT_TIMEOUT_S; the console only
                        opens once the Pi answers, otherwise the dialog stays open.
    DEMO MODE ......... opens the console with a simulated vehicle (nothing transmitted)
    VIEW LOGS ......... saved console session logs (logs/): preview, export, delete
    VIEW RECORDINGS ... camera recordings (recordings/): built-in player, marks, open folder
    CONTROLLER MAP .... DualShock 3 and Xbox button maps side by side
    CONTROLLER PROFILES calibrate a controller (drift, deadzone, range) and save it
    QUIT .............. closes the program

Navigation: mouse, or arrow keys / Tab (Shift+Tab goes up) + Enter / Esc. The game controller does not navigate the
menu or its cards; it is only read here by CONTROLLER PROFILES (calibration). It drives
the console (main window), including demo mode.
The dialogs are drawn as cards over a dimmed menu, like the design, rather than as
separate windows. Each card has its own file next to this one (ui/menu/):

    connect.py ............. CONNECT VEHICLE        logs.py ......... VIEW LOGS
    recordings.py .......... VIEW RECORDINGS        controller_map.py  CONTROLLER MAP
    controller_profiles.py . CONTROLLER PROFILES    cards.py ........ Card, Overlay, ResizeGrip, buttons
"""

from pathlib import Path

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QPainter, QPen, QPixmap, QRadialGradient,
                           QTransform)
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from command_center_py.config import APP_BUILD, APP_VERSION
from command_center_py.controller import profiles as cp
from command_center_py.ui.menu.cards import OK_BORDER, Overlay, RED_BORDER, SOFT, slab, spaced
from command_center_py.ui.menu.connect import ConnectCard
from command_center_py.ui.menu.controller_map import ControllerMapCard
from command_center_py.ui.menu.controller_profiles import ControllerProfilesCard
from command_center_py.ui.menu.logs import LogsCard
from command_center_py.ui.menu.recordings import RecordingsCard
from command_center_py.ui.theme import (ACCENT, BORDER, BORDER2, BRIGHT, DANGER, GRID, HEAD, LABEL,
                                        MUTED, OFF, SANS, lab, mono)

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:          # QtSvg missing - the menu just shows no logo
    QSvgRenderer = None


LOGO_SVG = Path(__file__).resolve().parent.parent / "assets" / "camosunrov-logo-dark.svg"


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
# MAIN MENU WINDOW
# ============================================================================
class MainMenu(QWidget):
    ITEMS = ("CONNECT VEHICLE", "DEMO MODE", "VIEW LOGS", "VIEW RECORDINGS", "CONTROLLER MAP", "CONTROLLER PROFILES", "QUIT")

    def __init__(self, pad, on_connected, on_demo):
        super().__init__()
        self.pad = pad
        self._on_connected, self._on_demo = on_connected, on_demo
        self.setWindowTitle("Camosun ROV — Command Centre")
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
        self.pad_name = None

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
        title = QLabel('<span style="font-size:60px">Camosun ROV</span> - Command Centre')
        title.setFont(spaced(mono(44, QFont.Weight.Bold), 0.9))
        title.setStyleSheet(f"color: {BRIGHT}; background: transparent;")
        tcol.addWidget(title)
        tcol.addWidget(lab(f"v{APP_VERSION} · {APP_BUILD}", 14, MUTED))
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
        self._hint(hints, "↑↓ / TAB", "NAVIGATE")
        self._hint(hints, "ENTER", "SELECT")
        self._hint(hints, "ESC", "BACK")
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
        self.rec_card = RecordingsCard(self.close_overlay)
        self.rec_ov = Overlay(self, self.rec_card, self.rec_card.close_card)
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
        elif item == "VIEW RECORDINGS":
            self.open_overlay(self.rec_ov)
            self.rec_card.opened()
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
        if ov in (self.map_ov, self.logs_ov, self.ctl_ov, self.rec_ov):
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
        for ov in (self.connect_ov, self.map_ov, self.logs_ov, self.ctl_ov, self.rec_ov):
            ov.setGeometry(self.rect())
        for card in (self.logs_card, self.rec_card):
            card.refit()                         # maximised cards follow the window

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
        if self.overlay is self.rec_ov:
            if not self.rec_card.key(e):
                super().keyPressEvent(e)
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

    def focusNextPrevChild(self, nxt):
        """Tab / Shift+Tab on the menu itself move the selection like Down / Up (wrapping).
        With a card open, Tab moves between that card's controls as normal."""
        if self.overlay is None:
            self.select(self.sel + (1 if nxt else -1))
            return True
        return super().focusNextPrevChild(nxt)

    # ---------------- controller ----------------
    # The controller does not navigate the menu or its cards (mouse / keyboard only).
    # It is read here just to show whether one is connected, and for calibration in
    # CONTROLLER PROFILES; it drives the console (main window), demo mode included.
    def pause(self):
        """Stop reading the controller (the console owns it while it is open)."""
        self.timer.stop()

    def resume(self):
        """Start reading the controller again (status line, CONTROLLER PROFILES)."""
        self.pad_name = None
        self.timer.start(50)
        self.tick()

    def tick(self):
        pad = self.pad.snapshot()
        name = pad.name if pad.connected else ""
        if name != self.pad_name:
            self.pad_name = name
            self.status_lbl.setText(f"Controller: {name or 'connected'} — drives the ROV in the console"
                                    if pad.connected else
                                    "No controller connected — one is needed to drive the ROV in the console")
        if self.overlay is self.ctl_ov:              # calibrating: the pad is input, not navigation
            self.ctl_card.update_pad(pad)

    def closeEvent(self, e):
        self.connect_card.abort_attempt()
        self.rec_card.player.close()          # stop the playback thread / release the file
        self.timer.stop()
        super().closeEvent(e)
