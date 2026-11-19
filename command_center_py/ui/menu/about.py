"""ABOUT card: version and build, a short overview, the system, the software used, the data
folder, links, then the licence.

The repository link is REPO_URL in config.py.
"""

import html
import platform
from importlib import metadata

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QPlainTextEdit, QScrollArea,
                               QVBoxLayout, QWidget)

from command_center_py.config import APP_BUILD, APP_DIR, APP_VERSION, DATA_DIR, FROZEN, RATE_HZ, REPO_URL
from command_center_py.ui.menu.cards import Card, SOFT, button
from command_center_py.ui.theme import (ACCENT, BORDER, BRIGHT, CONSOLE_FONT_SCALE, DANGER, GRID, HEAD, LABEL,
                                        MUTED, PANEL, WELL, lab, mono)

# Short overview shown under the version line.
OVERVIEW = ("Topside control software for the Camosun ROV. It reads a game controller (Xbox or PS3): "
            "the sticks and triggers drive six thrusters, the D-pad tilts the camera, and the buttons "
            "handle arming, E-STOP, thrust gain and the other console functions (see CONTROLLER MAP). "
            f"Commands go over the tether to the ROV at {RATE_HZ} Hz. It shows the live camera and "
            "telemetry (depth, attitude, temperatures, battery, leak), and records video and a "
            "timestamped event log of each dive.")

# The ROV itself (shown as SYSTEM). SI units.
SYSTEM = [
    ("Topside", "This program on a Windows laptop, game controller (Xbox or PS3)"),
    ("Tether", "33 m Blue Robotics Fathom tether, Ethernet to the Pi"),
    ("ROV computer", "Raspberry Pi 4: camera (H.264), commands and telemetry"),
    ("Controller", "STM32F446RE: thrusters, tilt servo, sensors, leak"),
    ("Thrusters", "4 horizontal (vectored) + 2 vertical"),
    ("Sensors", "Bar30 depth, temperatures, IMU, leak"),
    ("Power", "Blue Robotics Li-ion 4S 18 Ah battery (14.8 V nominal)"),
]

# Open-source libraries the program uses: (name, package for its version, licence)
LIBRARIES = [
    ("PySide6 (Qt)", "PySide6", "LGPL-3.0"),
    ("pygame-ce (SDL)", "pygame-ce", "LGPL-2.1"),
    ("PyAV (FFmpeg)", "av", "BSD-3-Clause"),
    ("openpyxl", "openpyxl", "MIT"),
]


def license_text():
    """The repo's LICENSE (bundled into the .exe by CamosunROV.spec)."""
    try:
        return (APP_DIR / "LICENSE").read_text(encoding="utf-8").strip()
    except OSError:
        return f"MIT License. The full text is in LICENSE at {REPO_URL}"


def _version(package):
    """Installed version of a package: from its metadata (doesn't import it, so PyAV's slow
    FFmpeg load isn't triggered here), else - e.g. inside the .exe, which may not carry the
    metadata - from the already-loaded module. '' if unknown."""
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        pass
    try:
        if package == "PySide6":
            import PySide6
            return PySide6.__version__
        if package == "pygame-ce":
            import pygame
            return pygame.version.ver
        if package == "openpyxl":
            import openpyxl
            return openpyxl.__version__
    except (ImportError, AttributeError):
        pass
    return ""


class _FitScroll(QScrollArea):
    """Scroll area that asks for its whole content's height (so the card is only as tall as it
    needs), but can be squeezed smaller by a short window - then it scrolls."""

    def __init__(self, content):
        super().__init__()
        self.setWidget(content)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def sizeHint(self):
        return self.widget().sizeHint()

    def minimumSizeHint(self):
        return QSize(self.widget().minimumSizeHint().width(), 80)


class AboutCard(Card):
    """ABOUT: Esc / Enter / ✕ / OK close it."""

    def __init__(self, on_close):
        z = lambda v: round(v * CONSOLE_FONT_SCALE)          # same text size as CONTROLLER MAPS
        super().__init__("ABOUT", 640, scale=CONSOLE_FONT_SCALE)
        self.close_btn.clicked.connect(on_close)
        # Everything scrolls inside the card, so on a short screen the card shrinks to fit the
        # window and gets a scroll bar instead of squashing its rows together.
        outer = QVBoxLayout(self.body)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        content.setObjectName("aboutContent")
        content.setStyleSheet("QWidget#aboutContent { background: transparent; }")
        v = QVBoxLayout(content)
        v.setContentsMargins(z(16), z(14), z(16), z(16))
        v.setSpacing(z(6))
        self.scroll = _FitScroll(content)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }}"
                                  f"QScrollArea > QWidget > QWidget {{ background: transparent; }}"
                                  f"QScrollBar:vertical {{ background: {PANEL}; border: none; width: {z(10)}px; }}"
                                  f"QScrollBar::handle:vertical {{ background: {GRID}; border-radius: 4px; min-height: 24px; }}"
                                  f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}")
        outer.addWidget(self.scroll)

        title = lab("Camosun ROV — Command Centre", z(16), BRIGHT, QFont.Weight.Bold)
        v.addWidget(title)
        v.addWidget(lab(f"Version {APP_VERSION} · build {APP_BUILD}" + ("  ·  Windows .exe" if FROZEN else ""),
                        z(11), ACCENT))
        overview = lab(f'<p style="line-height: 130%">{html.escape(OVERVIEW)}</p>', z(11), SOFT)
        overview.setTextFormat(Qt.TextFormat.RichText)          # rich text for the line spacing
        overview.setWordWrap(True)
        overview.setContentsMargins(0, z(10), 0, 0)
        v.addWidget(overview)

        def section(name, rows, key_w=130):
            head = lab(name, z(9), MUTED)
            head.setContentsMargins(0, z(12), 0, z(2))
            v.addWidget(head)
            g = QGridLayout()
            g.setHorizontalSpacing(z(12))
            g.setVerticalSpacing(z(4))
            for r, (k, val) in enumerate(rows):
                kl = lab(k, z(11), LABEL)
                kl.setFixedWidth(z(key_w))
                kl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                vl = lab(val, z(11), SOFT)
                vl.setWordWrap(True)
                g.addWidget(kl, r, 0)
                g.addWidget(vl, r, 1)
            g.setColumnStretch(1, 1)
            v.addLayout(g)

        section("SYSTEM", SYSTEM)
        libs = [(name, f"{_version(pkg) or '—'}  ·  {lic}") for name, pkg, lic in LIBRARIES]
        section("SOFTWARE AND LICENCES", [("Python", platform.python_version())] + libs)

        # data folder: where profiles, logs and recordings are saved
        head = lab("DATA FOLDER", z(9), MUTED)
        head.setContentsMargins(0, z(12), 0, z(2))
        v.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(z(12))
        path = lab(str(DATA_DIR), z(11), SOFT)
        path.setWordWrap(True)
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)   # can be copied
        row.addWidget(path, 1)
        folder = button("OPEN DATA FOLDER", z(11), None,
                        f"padding: 6px 12px; border: 1px solid {GRID}; border-radius: 3px; background: {HEAD}; color: {SOFT};",
                        f"border-color: {ACCENT}; color: {ACCENT};")
        folder.clicked.connect(self._open_data_folder)
        row.addWidget(folder, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(row)
        self.data_note = lab("Vehicle and controller profiles, logs and recordings", z(10), LABEL)
        self.data_note.setWordWrap(True)
        v.addWidget(self.data_note)

        # links, then the licence
        head = lab("LINKS", z(9), MUTED)
        head.setContentsMargins(0, z(12), 0, z(2))
        v.addWidget(head)
        for url, text in ((REPO_URL, REPO_URL), (f"{REPO_URL}/releases", "Releases (download CamosunROV.zip)")):
            link = QLabel(f'<a href="{url}" style="color:{ACCENT}; text-decoration:none">{text}</a>')
            link.setFont(lab("", z(11)).font())
            link.setOpenExternalLinks(True)                  # opens in the default browser
            link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            link.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            link.setStyleSheet("background: transparent;")
            v.addWidget(link)

        head = lab("LICENCE", z(9), MUTED)
        head.setContentsMargins(0, z(12), 0, z(2))
        v.addWidget(head)
        box = QPlainTextEdit(license_text())
        box.setReadOnly(True)
        box.setFont(mono(z(10)))
        box.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        box.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        box.setFixedHeight(z(275))                          # scrolls; the full text is 21 lines
        box.setStyleSheet(f"QPlainTextEdit {{ background: {WELL}; color: {SOFT}; border: 1px solid {BORDER};"
                          f" border-radius: 3px; padding: {z(6)}px; }}"
                          f"QScrollBar {{ background: {PANEL}; border: none; width: {z(10)}px; }}"
                          f"QScrollBar::handle {{ background: {GRID}; border-radius: 4px; min-height: 24px; }}"
                          f"QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}")
        v.addWidget(box)

        self.foot_lay.addWidget(lab("ESC", z(10), SOFT))
        self.foot_lay.addWidget(lab("to close", z(10), LABEL))
        self.foot_lay.addStretch(1)
        ok = button("OK", z(11), z(72),
                    f"padding: 6px 0; border: 1px solid {GRID}; border-radius: 3px; background: #1a2029; color: {BRIGHT};",
                    f"border-color: {ACCENT}; color: {ACCENT};")
        ok.clicked.connect(on_close)
        self.foot_lay.addWidget(ok)
        self.setFixedWidth(max(self.width(), self.sizeHint().width() + 8))

    def _open_data_folder(self):
        try:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            self.data_note.setStyleSheet(f"color: {DANGER}; background: transparent;")
            self.data_note.setText(f"Can't open the data folder — {e}")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(DATA_DIR)))
