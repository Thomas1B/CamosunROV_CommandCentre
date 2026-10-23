"""Colours and fonts (from the ROV Control Console mockup) plus a label helper."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel

# ── Backgrounds (darkest → lightest) ─────────────────────────────
# BG    - main window background
# PANEL - side panel background
# HEAD  - section header strips (e.g. "THRUSTER OUTPUT")
# WELL  - darkest; inside of recessed areas: stick pads, bars, input boxes
BG, PANEL, HEAD, WELL = "#0b0f14", "#0e131a", "#131a22", "#070a0e"

# ── Lines ────────────────────────────────────────────────────────
# BORDER  - standard thin divider line between panels/sections
# BORDER2 - slightly lighter border for chips, boxes and dialogs
# GRID    - grid/guide lines (e.g. dashed deadzone circle in stick pads)
BORDER, BORDER2, GRID = "#1f2933", "#23303c", "#2c3a48"

# ── Text (brightest → dimmest: BRIGHT, TEXT, DIM, LABEL, MUTED) ──
# TEXT   - normal body text
# BRIGHT - near-white; headline numbers and important values
# MUTED  - faintest; hints, units, secondary info
# DIM    - softer secondary text
# LABEL  - small field/section labels
TEXT, BRIGHT, MUTED, DIM, LABEL = "#d7e0ea", "#eaf2fa", "#5f7183", "#9fb0c2", "#8fa2b5"

# ── Status colours ───────────────────────────────────────────────
# ACCENT - teal-green brand colour; OK / armed / active values
# WARN   - yellow; warnings and the camera tilt readout
# DANGER - red; E-STOP and errors
# BLUE   - blue highlight (e.g. LINK tag in the event log)
# OFF    - dark grey; inactive items (e.g. thruster at 0%)
ACCENT, WARN, DANGER, BLUE, OFF = "#35d0a5", "#ffd479", "#ff6b6e", "#7fb2ff", "#4d5d6d"

MONO = ["IBM Plex Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]
SANS = ["IBM Plex Sans", "Segoe UI", "DejaVu Sans", "sans-serif"]


# Console text is drawn this much bigger than the original mockup sizes (1.0 = mockup).
# Applies to the control console only - the main menu keeps the design sizes.
# Not scaled: the right-panel readings, which use VALUE_PX / UNIT_PX below.
CONSOLE_FONT_SCALE = 1.25


# Right-panel readings (telemetry cards, heading, roll/pitch/yaw, battery voltage): one size for
# every number and one for every unit, so the panel reads as a single column of data.
# Matches the UI design: values 16 pt, units / status values 12 pt (CSS pt = 4/3 px).
VALUE_PX = 21            # 16 pt
UNIT_PX = 16             # 12 pt


def fs(px):
    """Console font size: px scaled by CONSOLE_FONT_SCALE."""
    return round(px * CONSOLE_FONT_SCALE)


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
