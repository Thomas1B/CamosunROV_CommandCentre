"""Colours and fonts (from the ROV Control Console mockup) plus a label helper."""

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel

BG, PANEL, HEAD, WELL = "#0b0f14", "#0e131a", "#131a22", "#070a0e"
BORDER, BORDER2, GRID = "#1f2933", "#23303c", "#2c3a48"
TEXT, BRIGHT, MUTED, DIM, LABEL = "#d7e0ea", "#eaf2fa", "#5f7183", "#9fb0c2", "#8fa2b5"
ACCENT, WARN, DANGER, BLUE, OFF = "#35d0a5", "#ffd479", "#ff6b6e", "#7fb2ff", "#4d5d6d"

MONO = ["IBM Plex Mono", "Cascadia Mono", "Consolas", "DejaVu Sans Mono", "monospace"]
SANS = ["IBM Plex Sans", "Segoe UI", "DejaVu Sans", "sans-serif"]


# Console text is drawn this much bigger than the original mockup sizes (1.0 = mockup).
# Applies to the control console only - the main menu keeps the design sizes.
# Not scaled (kept as designed): HUD depth / thrust gain / heading / clock, battery
# voltage, and the four telemetry cards (depth, pressure, water temp, internal temp).
CONSOLE_FONT_SCALE = 1.25


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
